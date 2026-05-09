"""Suite spec parser + runner.

Loads a YAML eval suite, runs each topic through ``run_pipeline``, applies
per-stage assertions, and aggregates the result.

Budget watchdog: when ``budget.max_usd_total`` is set, a background task
samples ``usage_module.snapshot()`` every couple of seconds and cancels the
in-flight run when the threshold is crossed. The interrupted topic is
recorded with ``failed_at=<stage at cancel>`` and the suite ends with
``budget_exhausted=True``. No further topics are started.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from decisionlab.eval import kgadmin
from decisionlab.eval.assertions import (
    AssertionContext,
    AssertionOutcome,
    SuiteAssertionContext,
    run_assertion,
    run_suite_assertion,
)
from decisionlab.eval.cost import estimate_usd
from decisionlab.eval.kgadmin import KGStats
from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.runner import run_pipeline
from decisionlab.router import Stage
from decisionlab.runtime import usage as usage_module

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

    from decisionlab.domain.ports import WebSearchPort
    from shared.services import Services

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Spec types — frozen dataclasses parsed from YAML
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TopicSpec:
    text: str
    expect: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    """Map of stage name (research/formalize/reason/build) → list of
    one-key assertion dicts. Empty stages are valid."""


@dataclass(frozen=True)
class SetupAction:
    """One pre-topic setup action declared in the suite YAML.

    Each action has a ``kind`` resolved by ``_dispatch_setup_action`` plus
    a free-form ``args`` mapping passed through to the handler.
    """

    kind: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SuiteSpec:
    name: str
    stages: tuple[Stage, ...]
    reset_kg_before: bool
    env_spec_path: Path | None
    project_root: Path
    reports_root: Path
    topics: tuple[TopicSpec, ...]
    max_usd_total: float | None
    source_path: Path | None = None
    suite_assertions: tuple[dict[str, Any], ...] = ()
    setup: tuple[SetupAction, ...] = ()

    @classmethod
    def from_yaml(cls, path: Path) -> SuiteSpec:
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict):
            raise ValueError(f"suite YAML must be a mapping, got {type(raw)}")

        # Default to ``[]`` (empty) so an offline suite that runs only
        # ``suite_assertions:`` can declare ``stages: []``.
        stages = tuple(
            _parse_stages(raw.get("stages") if "stages" in raw else ["research"])
        )
        env_spec_path = (
            Path(raw["env_spec"]).expanduser().resolve()
            if raw.get("env_spec")
            else None
        )
        if Stage.REASON in stages or Stage.BUILD in stages:
            if env_spec_path is None:
                raise ValueError(
                    f"suite {raw.get('name', '?')!r}: env_spec required when "
                    "stages include reason or build"
                )
            if not env_spec_path.exists():
                raise FileNotFoundError(f"env_spec not found: {env_spec_path}")

        topics: list[TopicSpec] = []
        for entry in raw.get("topics") or []:
            if isinstance(entry, str):
                topics.append(TopicSpec(text=entry))
                continue
            if not isinstance(entry, dict):
                raise ValueError(f"topic entry must be string or mapping: {entry!r}")
            text = entry.get("text") or entry.get("topic")
            if not text:
                raise ValueError(f"topic entry missing text: {entry!r}")
            expect = entry.get("expect") or {}
            if not isinstance(expect, dict):
                raise ValueError(
                    f"topic {text!r} expect: must be a mapping, got {type(expect)}"
                )
            topics.append(TopicSpec(text=text, expect=expect))

        budget = raw.get("budget") or {}
        max_usd = budget.get("max_usd_total")
        max_usd = float(max_usd) if max_usd is not None else None

        raw_suite_assertions = raw.get("suite_assertions") or []
        if not isinstance(raw_suite_assertions, list):
            raise ValueError(
                f"suite {raw.get('name', '?')!r}: suite_assertions must be a list"
            )
        suite_assertions = tuple(raw_suite_assertions)

        setup = tuple(_parse_setup(raw.get("setup"), suite_name=raw.get("name", "?")))

        return cls(
            name=raw.get("name", path.stem),
            stages=stages,
            reset_kg_before=bool(raw.get("reset_kg_before", False)),
            env_spec_path=env_spec_path,
            project_root=Path(raw.get("project_root", "evals/runs")).expanduser(),
            reports_root=Path(raw.get("reports_root", "evals/runs")).expanduser(),
            topics=tuple(topics),
            max_usd_total=max_usd,
            source_path=path,
            suite_assertions=suite_assertions,
            setup=setup,
        )


def _parse_stages(raw: list[str] | str | None) -> list[Stage]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    valid = {s.value: s for s in Stage}
    out: list[Stage] = []
    for entry in raw:
        if entry not in valid:
            raise ValueError(f"unknown stage {entry!r}; valid: {sorted(valid)}")
        out.append(valid[entry])
    return out


def _parse_setup(raw: object, *, suite_name: str) -> list[SetupAction]:
    """Parse a YAML ``setup:`` block into a list of ``SetupAction``.

    A missing/empty block is valid and yields ``[]``. Each entry must be a
    mapping with a ``kind`` string; ``args`` is optional and defaults to
    ``{}``. Unknown ``kind`` values are *not* validated here — that lives
    in the dispatcher so a typo surfaces at run time rather than at parse
    time of every imported suite.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(
            f"suite {suite_name!r}: setup must be a list, got {type(raw).__name__}"
        )
    out: list[SetupAction] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(
                f"suite {suite_name!r}: setup entry must be a mapping, got {entry!r}"
            )
        kind = entry.get("kind")
        if not isinstance(kind, str) or not kind:
            raise ValueError(
                f"suite {suite_name!r}: setup entry missing 'kind' string: {entry!r}"
            )
        args = entry.get("args") or {}
        if not isinstance(args, dict):
            raise ValueError(
                f"suite {suite_name!r}: setup args must be a mapping: {entry!r}"
            )
        out.append(SetupAction(kind=kind, args=dict(args)))
    return out


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TopicResult:
    topic: str
    run: PipelineRunResult
    assertions: dict[str, list[AssertionOutcome]]
    """Map of stage name → list of assertion outcomes, in YAML order."""

    @property
    def all_passed(self) -> bool:
        return all(a.passed for outs in self.assertions.values() for a in outs)

    def total_assertions(self) -> int:
        return sum(len(outs) for outs in self.assertions.values())

    def failed_count(self) -> int:
        return sum(1 for outs in self.assertions.values() for a in outs if not a.passed)


@dataclass(frozen=True)
class SuiteResult:
    suite: SuiteSpec
    topic_results: tuple[TopicResult, ...]
    pre_stats: KGStats | None
    post_stats: KGStats | None
    total_usd: float
    duration_ms: int
    budget_exhausted: bool
    error: str | None = None
    suite_assertions: tuple[AssertionOutcome, ...] = ()

    @property
    def all_passed(self) -> bool:
        return (
            self.error is None
            and not self.budget_exhausted
            and all(t.all_passed for t in self.topic_results)
            and all(o.passed for o in self.suite_assertions)
        )

    def topics_run(self) -> int:
        return len(self.topic_results)


# ---------------------------------------------------------------------------
# Eval-KG segregation guard
# ---------------------------------------------------------------------------


_EVAL_MARKER_ENV = "LABTFG_EVAL_KG"
_EVAL_MARKER_TRUE = frozenset({"1", "true", "yes", "on"})

# Match the marker token as a *delimited* identifier so an arbitrary
# substring collision (e.g. a host named ``evaluation-prod.internal``)
# does NOT accidentally pass the guard. Token boundaries are anything
# that's not [a-z0-9].
_EVAL_TOKEN = "eval"
_EVAL_TOKEN_RE = re.compile(
    r"(?:^|[^a-z0-9])" + _EVAL_TOKEN + r"(?:[^a-z0-9]|$)",
    re.IGNORECASE,
)

_EVAL_GUARD_HINT = (
    f"Set {_EVAL_MARKER_ENV}=1 if this Neo4j instance is dedicated to evals, "
    f"or include {_EVAL_TOKEN!r} as a delimited token in NEO4J_URI "
    "/ NEO4J_DATABASE (e.g. bolt://eval-neo4j:7687)."
)


def _has_eval_token(value: str) -> bool:
    return bool(_EVAL_TOKEN_RE.search(value))


def _is_eval_kg() -> bool:
    """Return True iff the active Neo4j is marked as an eval instance.

    Three positive signals (any one is enough):

    1. ``LABTFG_EVAL_KG`` env var is truthy.
    2. ``NEO4J_URI`` carries the ``eval`` token bounded by non-alphanumerics
       (so ``bolt://eval-neo4j:7687`` passes, ``bolt://evaluation-prod``
       does NOT — guarding against substring collision on a prod host).
    3. ``NEO4J_DATABASE`` carries the same delimited token.
    """
    marker = os.environ.get(_EVAL_MARKER_ENV, "").strip().lower()
    if marker in _EVAL_MARKER_TRUE:
        return True
    uri = os.environ.get("NEO4J_URI", "")
    db = os.environ.get("NEO4J_DATABASE", "")
    return _has_eval_token(uri) or _has_eval_token(db)


def _assert_eval_kg_segregation() -> None:
    """Refuse to wipe a Neo4j instance that isn't marked as an eval KG.

    The eval suites assume they own the KG and reset it between runs.
    Pointing them at a prod or shared dev instance would silently destroy
    data, so the guard fails *closed*: if the marker is missing the suite
    aborts before the destructive Cypher fires.
    """
    if _is_eval_kg():
        return
    raise RuntimeError(
        "Refusing to reset KG: the configured Neo4j instance is not marked "
        "as an eval KG. " + _EVAL_GUARD_HINT
    )


# ---------------------------------------------------------------------------
# Setup-action dispatcher
# ---------------------------------------------------------------------------


async def _dispatch_setup_action(action: SetupAction, services: Services) -> None:
    """Resolve a suite-level setup action and run it.

    Each ``kind`` is a small, well-known operation that prepares the eval
    KG before topics start. Unknown kinds raise rather than silently
    skipping — a typo'd action shouldn't quietly leave the KG empty.
    """
    if action.kind == "seed_canonical_paradigms":
        await _run_seed_canonical_paradigms(action.args, services)
        return
    raise ValueError(
        f"unknown setup action kind: {action.kind!r}; "
        "supported: ['seed_canonical_paradigms']"
    )


async def _run_seed_canonical_paradigms(
    args: dict[str, Any], services: Services
) -> None:
    from decisionlab.knowledge.seed import seed_canonical_paradigms

    if services.kg is None:
        raise RuntimeError(
            "setup action 'seed_canonical_paradigms' needs a live KG; "
            "init_services() did not produce one"
        )
    raw_path = args.get("fixture_path")
    fixture_path = Path(raw_path).expanduser() if raw_path else None
    counters = await seed_canonical_paradigms(
        services.kg,
        services.embeddings,
        services.vectors,
        fixture_path=fixture_path,
    )
    logger.info(
        "Setup seed_canonical_paradigms: created=%d merged=%d vectors=%d",
        counters["nodes_created"],
        counters["nodes_merged"],
        counters["vectors_indexed"],
    )


# ---------------------------------------------------------------------------
# Budget watchdog
# ---------------------------------------------------------------------------


class BudgetExhaustedError(RuntimeError):
    """Raised by the watchdog when ``estimate_usd(usage)`` exceeds the cap."""


async def _run_with_budget(
    coro_factory,
    *,
    max_usd: float,
    check_interval: float = 2.0,
):
    """Run ``coro_factory()`` with a budget watchdog.

    Cancels the run task and raises ``BudgetExhaustedError`` when cumulative
    usage cost crosses the threshold. The factory is re-callable on each
    invocation (useful when retrying with a larger budget); we await it
    once here.
    """
    import contextlib

    task = asyncio.create_task(coro_factory())
    try:
        while not task.done():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=check_interval)
            cost = estimate_usd(usage_module.snapshot())
            if cost > max_usd:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
                raise BudgetExhaustedError(
                    f"estimated ${cost:.2f} > cap ${max_usd:.2f}"
                )
        return task.result()
    finally:
        if not task.done():
            task.cancel()


# ---------------------------------------------------------------------------
# Suite runner
# ---------------------------------------------------------------------------


async def run_suite(
    spec: SuiteSpec,
    *,
    services: Services,
    client: AsyncAnthropic,
    search: WebSearchPort,
    skip_kg_ops: bool = False,
) -> SuiteResult:
    """Execute a suite end-to-end. ``init_services()`` must have been called.

    ``skip_kg_ops=True`` disables every KG-touching call (reset, stats,
    assertions like ``min_nodes``). Used by tests that don't have a live
    Neo4j; production runs should leave it at False.
    """
    t0 = time.monotonic()
    pre_stats: KGStats | None = None
    post_stats: KGStats | None = None
    topic_results: list[TopicResult] = []
    budget_exhausted = False
    suite_error: str | None = None

    if spec.reset_kg_before and not skip_kg_ops:
        try:
            _assert_eval_kg_segregation()
            await kgadmin.reset(services, confirm=True)
            logger.info("Suite %r: reset KG before run", spec.name)
        except Exception as exc:
            suite_error = f"KG reset failed: {exc}"
            return _empty_suite_result(spec, t0, suite_error)

    if spec.setup and not skip_kg_ops:
        try:
            for action in spec.setup:
                await _dispatch_setup_action(action, services)
                logger.info("Suite %r: ran setup action %r", spec.name, action.kind)
        except Exception as exc:
            suite_error = f"setup action failed: {exc}"
            return _empty_suite_result(spec, t0, suite_error)

    if not skip_kg_ops:
        try:
            pre_stats = await kgadmin.stats(services)
        except Exception as exc:
            logger.warning("Suite %r: pre-stats failed: %s", spec.name, exc)

    for topic in spec.topics:
        if budget_exhausted:
            logger.warning(
                "Suite %r: budget exhausted, skipping remaining topics",
                spec.name,
            )
            break

        async def _topic_factory(topic=topic):
            return await run_pipeline(
                topic.text,
                services=services,
                stages=spec.stages,
                env_spec_path=spec.env_spec_path,
                project_root=spec.project_root,
                client=client,
                search=search,
                reports_root=spec.reports_root,
                reset_usage=False,  # accumulate across topics for budget tracking
            )

        try:
            if spec.max_usd_total is not None:
                pipeline_result = await _run_with_budget(
                    _topic_factory, max_usd=spec.max_usd_total
                )
            else:
                pipeline_result = await _topic_factory()
        except BudgetExhaustedError as exc:
            logger.warning(
                "Suite %r: budget exhausted on topic %r: %s", spec.name, topic.text, exc
            )
            budget_exhausted = True
            # Synthesize a partial result so the topic still appears in the report.
            pipeline_result = PipelineRunResult(
                run_id="<budget-exhausted>",
                topic=topic.text,
                stages_run=spec.stages,
                failed_at=Stage.RESEARCH,
                error=str(exc),
            )

        # Run assertions for each stage that has any.
        assertions_per_stage: dict[str, list[AssertionOutcome]] = {}
        ctx = AssertionContext(result=pipeline_result, services=services)
        for stage_name, stage_assertions in topic.expect.items():
            outs: list[AssertionOutcome] = []
            for spec_dict in stage_assertions or []:
                if _is_kg_assertion(spec_dict) and skip_kg_ops:
                    outs.append(
                        AssertionOutcome(
                            name=next(iter(spec_dict)),
                            passed=False,
                            detail="skipped: skip_kg_ops=True",
                        )
                    )
                    continue
                outs.append(await run_assertion(spec_dict, ctx))
            assertions_per_stage[stage_name] = outs

        topic_results.append(
            TopicResult(
                topic=topic.text,
                run=pipeline_result,
                assertions=assertions_per_stage,
            )
        )

    if not skip_kg_ops:
        try:
            post_stats = await kgadmin.stats(services)
        except Exception as exc:
            logger.warning("Suite %r: post-stats failed: %s", spec.name, exc)

    suite_outcomes: list[AssertionOutcome] = []
    if spec.suite_assertions:
        sctx = SuiteAssertionContext(
            suite=spec,
            topic_results=tuple(topic_results),
            pre_stats=pre_stats,
            post_stats=post_stats,
        )
        for sa_spec in spec.suite_assertions:
            suite_outcomes.append(await run_suite_assertion(sa_spec, sctx))

    duration_ms = int((time.monotonic() - t0) * 1000)
    total_usd = estimate_usd(usage_module.snapshot())
    return SuiteResult(
        suite=spec,
        topic_results=tuple(topic_results),
        pre_stats=pre_stats,
        post_stats=post_stats,
        total_usd=total_usd,
        duration_ms=duration_ms,
        budget_exhausted=budget_exhausted,
        error=suite_error,
        suite_assertions=tuple(suite_outcomes),
    )


def _empty_suite_result(spec: SuiteSpec, t0: float, error: str) -> SuiteResult:
    return SuiteResult(
        suite=spec,
        topic_results=(),
        pre_stats=None,
        post_stats=None,
        total_usd=0.0,
        duration_ms=int((time.monotonic() - t0) * 1000),
        budget_exhausted=False,
        error=error,
    )


_KG_ASSERTION_NAMES = frozenset(
    {
        "min_nodes",
        "relation_exists",
        "paradigm_reused",
        "min_memories",
        "confidence_above",
    }
)


def _is_kg_assertion(spec_dict: dict) -> bool:
    if not isinstance(spec_dict, dict) or not spec_dict:
        return False
    name = next(iter(spec_dict))
    return name in _KG_ASSERTION_NAMES


def parse_stages(raw: Iterable[str]) -> tuple[Stage, ...]:
    """Public helper for the CLI's --stages override."""
    return tuple(_parse_stages(list(raw)))

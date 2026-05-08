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
    client: AsyncAnthropic,
    search: WebSearchPort,
    skip_kg_ops: bool = False,
) -> SuiteResult:
    """Execute a suite end-to-end. ``shared.init()`` must have been called.

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
            await kgadmin.reset(confirm=True)
            logger.info("Suite %r: reset KG before run", spec.name)
        except Exception as exc:
            suite_error = f"KG reset failed: {exc}"
            return _empty_suite_result(spec, t0, suite_error)

    if not skip_kg_ops:
        try:
            pre_stats = await kgadmin.stats()
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
        ctx = AssertionContext(result=pipeline_result)
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
            post_stats = await kgadmin.stats()
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

"""Assertion predicates for eval suites.

Each suite YAML entry under ``expect:`` is one ``{predicate_name: args}``
dict. The predicate runs against either the topic's ``PipelineRunResult``
(checks against pipeline outputs) or the live KG (checks against post-run
graph state). All predicates return an ``AssertionOutcome`` carrying
``passed`` plus a human-readable ``detail`` for the report.

Adding a predicate: write an async function with signature
``(ctx, args) -> AssertionOutcome``, decorate with ``@register("name")``.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decisionlab.eval.kgadmin import query as kg_query
from decisionlab.eval.models import PipelineRunResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssertionOutcome:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class AssertionContext:
    """What an assertion can read from. Pipeline-result predicates use
    ``result``; KG predicates ignore it and call ``kg_query`` directly."""

    result: PipelineRunResult


PredicateFn = Callable[[AssertionContext, Any], Awaitable[AssertionOutcome]]
_REGISTRY: dict[str, PredicateFn] = {}


def register(name: str) -> Callable[[PredicateFn], PredicateFn]:
    """Decorator: bind a predicate function to a YAML key name."""

    def _wrap(fn: PredicateFn) -> PredicateFn:
        if name in _REGISTRY:
            raise RuntimeError(f"predicate {name!r} already registered")
        _REGISTRY[name] = fn
        return fn

    return _wrap


def predicate_names() -> list[str]:
    return sorted(_REGISTRY.keys())


async def run_assertion(
    spec: dict[str, Any],
    ctx: AssertionContext,
) -> AssertionOutcome:
    """Resolve a one-key dict like ``{paradigm: rl}`` to the predicate
    and execute it. Unknown keys produce a failed outcome with a clear
    error so a typo in YAML is reported, not crashed."""
    if not isinstance(spec, dict) or len(spec) != 1:
        return AssertionOutcome(
            name="<malformed>",
            passed=False,
            detail=(
                f"assertion spec must be a single-key dict, got {spec!r}. "
                f"valid predicates: {predicate_names()}"
            ),
        )
    name, args = next(iter(spec.items()))
    fn = _REGISTRY.get(name)
    if fn is None:
        return AssertionOutcome(
            name=name,
            passed=False,
            detail=f"unknown predicate {name!r}; valid: {predicate_names()}",
        )
    try:
        return await fn(ctx, args)
    except Exception as exc:
        logger.exception("assertion %s crashed", name)
        return AssertionOutcome(
            name=name,
            passed=False,
            detail=f"predicate raised: {exc!r}",
        )


# ---------------------------------------------------------------------------
# Pipeline-result predicates
# ---------------------------------------------------------------------------


@register("paradigm")
async def _paradigm_present(ctx: AssertionContext, slug: str) -> AssertionOutcome:
    """Pass when the named paradigm slug is in ``result.paradigms``."""
    found = slug in ctx.result.paradigms
    return AssertionOutcome(
        name="paradigm",
        passed=found,
        detail=(
            f"paradigm {slug!r} {'present' if found else 'absent'} — "
            f"discovered: {list(ctx.result.paradigms)}"
        ),
    )


@register("has_formulation")
async def _has_formulation(ctx: AssertionContext, slug: str) -> AssertionOutcome:
    found = slug in ctx.result.formulations
    return AssertionOutcome(
        name="has_formulation",
        passed=found,
        detail=(
            f"formulation for {slug!r} "
            f"{'present' if found else 'absent'} — "
            f"available: {list(ctx.result.formulations)}"
        ),
    )


@register("min_paradigms")
async def _min_paradigms(ctx: AssertionContext, n: int) -> AssertionOutcome:
    actual = len(ctx.result.paradigms)
    return AssertionOutcome(
        name="min_paradigms",
        passed=actual >= n,
        detail=f"discovered {actual} paradigms (threshold ≥ {n})",
    )


@register("succeeded")
async def _succeeded(ctx: AssertionContext, _arg: Any) -> AssertionOutcome:
    """Trivial gate — fails when the pipeline crashed mid-run."""
    return AssertionOutcome(
        name="succeeded",
        passed=ctx.result.succeeded,
        detail=(
            "pipeline succeeded"
            if ctx.result.succeeded
            else f"pipeline failed at {ctx.result.failed_at}: {ctx.result.error}"
        ),
    )


# ---------------------------------------------------------------------------
# KG predicates
# ---------------------------------------------------------------------------


@register("min_nodes")
async def _min_nodes(ctx: AssertionContext, args: dict) -> AssertionOutcome:
    """Pass when at least *n* nodes of *label* exist in the KG.

    YAML: ``min_nodes: { label: Paradigm, n: 3 }``
    """
    label = args.get("label")
    n = int(args.get("n", 1))
    if not label:
        return AssertionOutcome(
            name="min_nodes", passed=False, detail="missing 'label' arg"
        )
    rows = await kg_query(f"MATCH (n:{label}) RETURN count(n) AS c")
    actual = int(rows[0]["c"]) if rows else 0
    return AssertionOutcome(
        name="min_nodes",
        passed=actual >= n,
        detail=f"{label}: {actual} nodes (threshold ≥ {n})",
    )


@register("relation_exists")
async def _relation_exists(ctx: AssertionContext, args: dict) -> AssertionOutcome:
    """Pass when at least one active relation matching the spec exists.

    YAML: ``relation_exists: { from: Paradigm, type: BELONGS_TO, to: Variable }``
    """
    from_label = args.get("from")
    to_label = args.get("to")
    rel_type = args.get("type")
    if not (from_label and to_label and rel_type):
        return AssertionOutcome(
            name="relation_exists",
            passed=False,
            detail="missing one of 'from'/'type'/'to' args",
        )
    rows = await kg_query(
        f"MATCH (a:{from_label})-[r:{rel_type}]->(b:{to_label}) "
        "WHERE r.valid_to IS NULL RETURN count(r) AS c"
    )
    actual = int(rows[0]["c"]) if rows else 0
    return AssertionOutcome(
        name="relation_exists",
        passed=actual > 0,
        detail=f"{from_label}-[{rel_type}]->{to_label}: {actual} active",
    )


# ---------------------------------------------------------------------------
# Builder-output predicates — load generated *_model.py and exercise
# ---------------------------------------------------------------------------


def _load_module_from(path: Path):
    """Load a .py file as an unnamed module — never registered globally
    so successive evals don't collide on module names."""
    spec = importlib.util.spec_from_file_location(f"_eval_module_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build importlib spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _find_artifact(artifacts: tuple[Path, ...], spec_id: str) -> Path | None:
    """Locate a built artifact by spec id substring."""
    for p in artifacts:
        if spec_id in p.name:
            return p
    return None


@register("module_imports")
async def _module_imports(ctx: AssertionContext, spec_id: str) -> AssertionOutcome:
    """Pass when the generated builder module for *spec_id* imports cleanly."""
    path = _find_artifact(ctx.result.builder_artifacts, spec_id)
    if path is None or not path.exists():
        return AssertionOutcome(
            name="module_imports",
            passed=False,
            detail=f"no builder artifact found for spec_id={spec_id!r}",
        )
    try:
        _load_module_from(path)
    except Exception as exc:
        return AssertionOutcome(
            name="module_imports",
            passed=False,
            detail=f"import failed: {exc!r}",
        )
    return AssertionOutcome(
        name="module_imports",
        passed=True,
        detail=f"imported {path.name} cleanly",
    )


@register("decide_returns_action")
async def _decide_returns_action(ctx: AssertionContext, args: dict) -> AssertionOutcome:
    """Pass when ``module.<Class>().decide(perception)`` returns a value
    that looks like an Action (string or dict with a 'kind'/'name' key).

    YAML::

        decide_returns_action:
          spec_id: rl-q-learning
          perception: { x: 0, y: 0, grid_width: 5, grid_height: 5,
                        step: 0, resources: [], last_action_result: null }
    """
    spec_id = args.get("spec_id")
    perception = args.get("perception", {})
    if not spec_id:
        return AssertionOutcome(
            name="decide_returns_action",
            passed=False,
            detail="missing 'spec_id' arg",
        )
    path = _find_artifact(ctx.result.builder_artifacts, spec_id)
    if path is None or not path.exists():
        return AssertionOutcome(
            name="decide_returns_action",
            passed=False,
            detail=f"no builder artifact found for spec_id={spec_id!r}",
        )
    try:
        module = _load_module_from(path)
    except Exception as exc:
        return AssertionOutcome(
            name="decide_returns_action",
            passed=False,
            detail=f"import failed: {exc!r}",
        )
    # Find a class that exposes a `decide` method.
    candidate = None
    for attr in dir(module):
        obj = getattr(module, attr)
        if isinstance(obj, type) and hasattr(obj, "decide"):
            candidate = obj
            break
    if candidate is None:
        return AssertionOutcome(
            name="decide_returns_action",
            passed=False,
            detail=f"no class with a `decide` method in {path.name}",
        )
    try:
        instance = candidate()
        action = instance.decide(perception)
    except Exception as exc:
        return AssertionOutcome(
            name="decide_returns_action",
            passed=False,
            detail=f"decide() raised: {exc!r}",
        )
    looks_like_action = isinstance(action, str) or (
        isinstance(action, dict) and ("kind" in action or "name" in action)
    )
    return AssertionOutcome(
        name="decide_returns_action",
        passed=looks_like_action,
        detail=(
            f"decide() returned {action!r}"
            + ("" if looks_like_action else " (not action-shaped)")
        ),
    )

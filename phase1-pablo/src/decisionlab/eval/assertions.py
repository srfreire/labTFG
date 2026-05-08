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
from typing import TYPE_CHECKING, Any

from decisionlab.eval.kgadmin import KGStats
from decisionlab.eval.kgadmin import query as kg_query
from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.timing import TimingLog

if TYPE_CHECKING:
    from decisionlab.eval.suite import SuiteSpec, TopicResult

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


@dataclass(frozen=True)
class SuiteAssertionContext:
    """What a suite-level predicate can read: full topic-result tuple,
    KG stats before/after, and the suite spec itself for cross-references."""

    suite: SuiteSpec | None
    topic_results: tuple[TopicResult, ...]
    pre_stats: KGStats | None
    post_stats: KGStats | None


SuitePredicateFn = Callable[[SuiteAssertionContext, Any], Awaitable[AssertionOutcome]]
_SUITE_REGISTRY: dict[str, SuitePredicateFn] = {}


def register_suite(name: str) -> Callable[[SuitePredicateFn], SuitePredicateFn]:
    """Decorator: bind a suite-level predicate function to a YAML key name."""

    def _wrap(fn: SuitePredicateFn) -> SuitePredicateFn:
        if name in _SUITE_REGISTRY:
            raise RuntimeError(f"suite predicate {name!r} already registered")
        _SUITE_REGISTRY[name] = fn
        return fn

    return _wrap


def suite_predicate_names() -> list[str]:
    return sorted(_SUITE_REGISTRY.keys())


async def run_suite_assertion(
    spec: dict[str, Any],
    ctx: SuiteAssertionContext,
) -> AssertionOutcome:
    """Resolve a one-key dict like ``{p95_below: {tool: ...}}`` to the
    suite predicate and execute it. Mirrors ``run_assertion`` but reads
    from a ``SuiteAssertionContext`` instead of a per-topic context."""
    if not isinstance(spec, dict) or len(spec) != 1:
        return AssertionOutcome(
            name="<malformed>",
            passed=False,
            detail=f"suite assertion must be a single-key dict, got {spec!r}",
        )
    name, args = next(iter(spec.items()))
    fn = _SUITE_REGISTRY.get(name)
    if fn is None:
        return AssertionOutcome(
            name=name,
            passed=False,
            detail=(
                f"unknown suite predicate {name!r}; valid: {suite_predicate_names()}"
            ),
        )
    try:
        return await fn(ctx, args)
    except Exception as exc:
        logger.exception("suite assertion %s crashed", name)
        return AssertionOutcome(
            name=name,
            passed=False,
            detail=f"suite predicate {name!r} raised: {exc}",
        )


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


@register("tool_called")
async def _tool_called(ctx: AssertionContext, args: dict) -> AssertionOutcome:
    """Pass when the pipeline made at least *min* calls to the named tool.

    YAML: ``tool_called: { name: retrieve_knowledge, min: 1 }``
    """
    name = args.get("name") if isinstance(args, dict) else None
    min_count = int(args.get("min", 1)) if isinstance(args, dict) else 1
    if not name:
        return AssertionOutcome(
            name="tool_called", passed=False, detail="missing 'name' arg"
        )
    actual = sum(1 for c in ctx.result.tool_call_log if c.name == name)
    return AssertionOutcome(
        name="tool_called",
        passed=actual >= min_count,
        detail=f"{name}: {actual} call(s) (threshold ≥ {min_count})",
    )


# ---------------------------------------------------------------------------
# Memory predicates — Qdrant + Postgres
# ---------------------------------------------------------------------------


@register("min_memories")
async def _min_memories(ctx: AssertionContext, args: dict) -> AssertionOutcome:
    """Pass when ≥ *n* memories exist in Postgres for the given namespace.

    YAML: ``min_memories: { namespace: paradigm, n: 5 }``
    """
    namespace = args.get("namespace") if isinstance(args, dict) else None
    n = int(args.get("n", 1)) if isinstance(args, dict) else 1
    if not namespace:
        return AssertionOutcome(
            name="min_memories", passed=False, detail="missing 'namespace' arg"
        )
    from sqlalchemy import func, select

    import shared
    from shared.models import Memory

    if shared.db is None:
        return AssertionOutcome(
            name="min_memories",
            passed=False,
            detail="shared.db unavailable",
        )
    async with shared.db.get_session() as session:
        stmt = select(func.count(Memory.id)).where(
            Memory.namespace == namespace,
            Memory.valid_to.is_(None),
        )
        result = await session.execute(stmt)
        actual = int(result.scalar() or 0)
    return AssertionOutcome(
        name="min_memories",
        passed=actual >= n,
        detail=f"namespace={namespace!r}: {actual} active memories (threshold ≥ {n})",
    )


@register("confidence_above")
async def _confidence_above(ctx: AssertionContext, args: dict) -> AssertionOutcome:
    """Pass when at least one memory whose content contains *fact_substring*
    has confidence ≥ *threshold*.

    YAML: ``confidence_above: { fact_substring: "Q-learning", threshold: 0.7 }``
    """
    fact_substring = args.get("fact_substring") if isinstance(args, dict) else None
    threshold = float(args.get("threshold", 0.5)) if isinstance(args, dict) else 0.5
    if not fact_substring:
        return AssertionOutcome(
            name="confidence_above",
            passed=False,
            detail="missing 'fact_substring' arg",
        )
    from sqlalchemy import select

    import shared
    from shared.models import Memory

    if shared.db is None:
        return AssertionOutcome(
            name="confidence_above", passed=False, detail="shared.db unavailable"
        )
    async with shared.db.get_session() as session:
        stmt = (
            select(Memory.confidence)
            .where(
                Memory.content.contains(fact_substring),
                Memory.valid_to.is_(None),
            )
            .order_by(Memory.confidence.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
    if row is None:
        return AssertionOutcome(
            name="confidence_above",
            passed=False,
            detail=f"no active memory matched {fact_substring!r}",
        )
    return AssertionOutcome(
        name="confidence_above",
        passed=row >= threshold,
        detail=(
            f"top match for {fact_substring!r}: confidence={row:.2f} "
            f"(threshold ≥ {threshold:.2f})"
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


@register("paradigm_reused")
async def _paradigm_reused(ctx: AssertionContext, slug: str) -> AssertionOutcome:
    """Pass when a Paradigm node with *slug* exists and was created BEFORE
    this run started — proves the run hit an existing node rather than
    minting one. Critical for validating canonicalization on a populated KG.
    """
    if not isinstance(slug, str) or not slug:
        return AssertionOutcome(
            name="paradigm_reused",
            passed=False,
            detail=f"expected paradigm slug string, got {slug!r}",
        )
    started_at = ctx.result.started_at
    if not started_at:
        return AssertionOutcome(
            name="paradigm_reused",
            passed=False,
            detail="run.started_at missing — cannot determine reuse",
        )
    rows = await kg_query(
        "MATCH (p:Paradigm {slug: $slug}) RETURN p.created_at AS created_at LIMIT 1",
        {"slug": slug},
    )
    if not rows:
        return AssertionOutcome(
            name="paradigm_reused",
            passed=False,
            detail=f"paradigm {slug!r} not in KG",
        )
    paradigm_at = rows[0].get("created_at")
    if not isinstance(paradigm_at, str):
        return AssertionOutcome(
            name="paradigm_reused",
            passed=False,
            detail=f"paradigm {slug!r} has no created_at — cannot determine reuse",
        )
    passed = paradigm_at < started_at
    return AssertionOutcome(
        name="paradigm_reused",
        passed=passed,
        detail=(
            f"paradigm {slug!r}: created_at={paradigm_at} "
            f"{'<' if passed else '>='} run.started_at={started_at}"
        ),
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


# ---------------------------------------------------------------------------
# Suite-level timing predicates
# ---------------------------------------------------------------------------


@register_suite("p95_below")
async def _p95_below(ctx: SuiteAssertionContext, args) -> AssertionOutcome:
    """Aggregate ToolCall.duration_ms across all topics and assert the
    per-tool p95 is below the configured threshold.

    args: {"tool": "retrieve_knowledge", "p95_ms": 2500}
    """
    tool = args["tool"]
    threshold = float(args["p95_ms"])
    all_calls: list = []
    for tr in ctx.topic_results:
        all_calls.extend(tr.run.tool_call_log)
    summary = TimingLog.summarize_tool_calls(all_calls)
    if tool not in summary:
        return AssertionOutcome(
            name="p95_below",
            passed=False,
            detail=f"no data for tool {tool!r} across topics",
        )
    p95 = summary[tool]["p95_ms"]
    return AssertionOutcome(
        name="p95_below",
        passed=p95 <= threshold,
        detail=f"{tool} p95={p95:.0f}ms threshold={threshold:.0f}ms",
    )


@register_suite("avg_below")
async def _avg_below(ctx: SuiteAssertionContext, args) -> AssertionOutcome:
    """Average stage duration across topics, asserting it's below threshold.

    args: {"stage": "canonicalize", "avg_ms": 8000}
    """
    stage = args["stage"]
    threshold = float(args["avg_ms"])
    durations: list[float] = []
    for tr in ctx.topic_results:
        if tr.run.timing is None:
            continue
        for st in tr.run.timing.stages:
            if st.stage == stage:
                durations.append(st.duration_ms)
    if not durations:
        return AssertionOutcome(
            name="avg_below",
            passed=False,
            detail=f"no data for stage {stage!r} across topics",
        )
    avg = sum(durations) / len(durations)
    return AssertionOutcome(
        name="avg_below",
        passed=avg <= threshold,
        detail=(
            f"{stage} avg={avg:.0f}ms (n={len(durations)}) threshold={threshold:.0f}ms"
        ),
    )


def _pair_text(node: Any, fallback: str = "") -> str:
    """Render a candidate/existing entry from the fixture as a single string.

    The canonicalize-pairs.json fixture stores ``{"name": ..., "description": ...}``
    objects so the verifier can reason about both. Some test fixtures use
    plain strings; both shapes are accepted.
    """
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        name = node.get("name", "").strip()
        desc = node.get("description", "").strip()
        if name and desc:
            return f"{name}: {desc}"
        return name or desc or fallback
    return fallback


@register_suite("merge_precision_recall")
async def _merge_precision_recall(ctx: SuiteAssertionContext, args) -> AssertionOutcome:
    """Run canonicalize._verify_merge over a labelled fixture and compute
    precision/recall/F1.

    Fixture layout (canonicalize-pairs.json):
        {"pairs": [{"label", "candidate"{name,description}, "existing"{...}, "should_merge"}, ...]}

    A bare list of pairs is also supported.

    args: {fixture: path, min_precision: 0.95, min_recall: 0.90}

    Cost: ~$0.05 per pair (one Sonnet call). 18-pair fixture ~ $1.
    """
    import json as _json
    from pathlib import Path as _Path

    fixture_path = _Path(args["fixture"])
    if not fixture_path.exists():
        return AssertionOutcome(
            name="merge_precision_recall",
            passed=False,
            detail=f"fixture not found: {fixture_path}",
        )
    min_precision = float(args.get("min_precision", 0.95))
    min_recall = float(args.get("min_recall", 0.90))

    try:
        raw = _json.loads(fixture_path.read_text())
    except _json.JSONDecodeError as exc:
        return AssertionOutcome(
            name="merge_precision_recall",
            passed=False,
            detail=f"fixture not valid JSON: {exc}",
        )
    pairs = raw.get("pairs") if isinstance(raw, dict) else raw
    if not isinstance(pairs, list) or not pairs:
        return AssertionOutcome(
            name="merge_precision_recall",
            passed=False,
            detail="fixture must contain a non-empty list of pairs",
        )

    # Late imports keep the heavy dep out of module load.
    from anthropic import AsyncAnthropic

    from decisionlab import canonicalize as _canon

    client = AsyncAnthropic()

    tp = fp = fn = tn = 0
    for p in pairs:
        candidate_text = _pair_text(p.get("candidate"))
        existing_text = _pair_text(p.get("existing"))
        decision = await _canon._verify_merge(
            label=p["label"],
            candidate_text=candidate_text,
            existing_text=existing_text,
            similarity=float(p.get("similarity", 0.0)),
            client=client,
        )
        predicted = bool(decision.merge)
        actual = bool(p["should_merge"])
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    passed = precision >= min_precision and recall >= min_recall
    return AssertionOutcome(
        name="merge_precision_recall",
        passed=passed,
        detail=(
            f"n={len(pairs)} tp={tp} fp={fp} fn={fn} tn={tn} "
            f"precision={precision:.3f} recall={recall:.3f} f1={f1:.3f} "
            f"thresholds: P>={min_precision:.2f} R>={min_recall:.2f}"
        ),
    )


def _normalize_topic_for_match(text: str) -> str:
    """Identity-style hash for matching topic text -> oracle entry.
    Robust to whitespace differences."""
    import hashlib as _hashlib

    cleaned = " ".join(text.split())
    return _hashlib.sha1(cleaned.encode("utf-8")).hexdigest()


@register_suite("slug_hit_rate")
async def _slug_hit_rate(ctx: SuiteAssertionContext, args) -> AssertionOutcome:
    """For each topic in topic_results, look up its oracle entry by text
    hash; count a hit if expected_slug appears anywhere in
    result.paradigms (liberal matching). Pass iff hits/total >= min_rate.

    args: {oracle: path, min_rate: 0.8}

    Topics not present in the oracle are skipped (don't count toward
    the denominator).
    """
    import json as _json
    from pathlib import Path as _Path

    oracle_path = _Path(args["oracle"])
    if not oracle_path.exists():
        return AssertionOutcome(
            name="slug_hit_rate",
            passed=False,
            detail=f"oracle not found: {oracle_path}",
        )
    min_rate = float(args.get("min_rate", 0.8))
    try:
        oracle = _json.loads(oracle_path.read_text())
    except _json.JSONDecodeError as exc:
        return AssertionOutcome(
            name="slug_hit_rate",
            passed=False,
            detail=f"oracle not valid JSON: {exc}",
        )

    by_hash = {
        _normalize_topic_for_match(p["topic_text"]): p["expected_slug"]
        for p in oracle
    }

    hits = 0
    total = 0
    misses: list[str] = []
    for tr in ctx.topic_results:
        h = _normalize_topic_for_match(tr.topic)
        expected = by_hash.get(h)
        if expected is None:
            continue
        total += 1
        if expected in tr.run.paradigms:
            hits += 1
        else:
            misses.append(f"{expected!r} not in {list(tr.run.paradigms)!r}")

    if total == 0:
        return AssertionOutcome(
            name="slug_hit_rate",
            passed=False,
            detail="no topic_results matched the oracle",
        )
    rate = hits / total
    detail = f"{hits}/{total} = {rate:.3f}, threshold={min_rate:.2f}"
    if misses:
        detail += "; misses: " + "; ".join(misses[:3])
        if len(misses) > 3:
            detail += f" (+{len(misses) - 3} more)"
    return AssertionOutcome(
        name="slug_hit_rate", passed=rate >= min_rate, detail=detail
    )


@register_suite("kg_growth_rate")
async def _kg_growth_rate(ctx: SuiteAssertionContext, args) -> AssertionOutcome:
    """Per-label growth rate (post - pre) / n_topics. Passes iff
    rate <= max_per_topic.

    args: {label: "Paradigm", max_per_topic: 1.5}
    """
    label = args["label"]
    max_per_topic = float(args["max_per_topic"])
    if ctx.pre_stats is None or ctx.post_stats is None:
        return AssertionOutcome(
            name="kg_growth_rate",
            passed=False,
            detail=f"missing pre/post stats — cannot compute growth for {label}",
        )
    n_topics = max(1, len(ctx.topic_results))
    pre_n = ctx.pre_stats.by_label.get(label, 0)
    post_n = ctx.post_stats.by_label.get(label, 0)
    delta = post_n - pre_n
    rate = delta / n_topics
    return AssertionOutcome(
        name="kg_growth_rate",
        passed=rate <= max_per_topic,
        detail=(
            f"{label}: pre={pre_n} post={post_n} Δ={delta:+d} "
            f"n={n_topics} rate={rate:.2f}/topic max={max_per_topic:.2f}"
        ),
    )

# Phase 0 — Eval Foundations & Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrument the eval harness with timing metrics and a fixture-driven `merge_precision_recall` predicate, ship a `merge-quality.yaml` suite, and capture the 2026-05-08 baseline numbers as the reference point for all later refactor phases.

**Architecture:** Two parallel additions to `decisionlab.eval`: (a) a `timing` module that piggybacks on the existing `runtime.tool_calls` ContextVar pattern to capture stage and tool-call durations into a `TimingLog`, threaded onto `PipelineRunResult`; (b) a `register_suite` decorator and `SuiteAssertionContext` so predicates that need cross-topic data (`merge_precision_recall`, `kg_growth_rate`, `p95_below`) can run after all topics finish. No core pipeline behaviour changes — these are pure observation hooks.

**Tech Stack:** Python 3.12, `pytest` + `pytest-asyncio`, `pyyaml`, `anthropic` (Sonnet 4.6 for `_verify_merge`), `pydantic` v2, `time.monotonic_ns()` for timing.

**Spec reference:** `phase1-pablo/docs/superpowers/specs/2026-05-08-memory-system-accuracy-refactor-design.md` — Phase 0 deliverables (D2, D5, D6).

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `phase1-pablo/src/decisionlab/eval/timing.py` | **new** | `StageTiming`, `ToolCallTiming`, `TimingLog`; ContextVar-backed collector + `record_stage()` context manager |
| `phase1-pablo/src/decisionlab/runtime/tool_calls.py` | modify | Extend `ToolCall` with `duration_ms: float \| None`; update `record()` to accept duration |
| `phase1-pablo/src/decisionlab/router.py` | modify | Wrap each `_run_stage` body with `timing.record_stage(stage)` |
| `phase1-pablo/src/decisionlab/eval/runner.py` | modify | Start a `TimingLog` alongside the tool-call log; thread onto `PipelineRunResult` |
| `phase1-pablo/src/decisionlab/eval/models.py` | modify | Add `timing: TimingLog \| None = None` field to `PipelineRunResult` |
| `phase1-pablo/src/decisionlab/eval/assertions.py` | modify | Introduce `SuiteAssertionContext` + `register_suite` registry; add `p95_below`, `avg_below`, `merge_precision_recall` predicates |
| `phase1-pablo/src/decisionlab/eval/suite.py` | modify | Parse `suite_assertions:` from YAML; run them after topic loop; carry results on `SuiteResult` |
| `phase1-pablo/src/decisionlab/eval/report.py` | modify | Render `timing.*` and `suite_assertions` sections in MD + JSON |
| `phase1-pablo/evals/suites/merge-quality.yaml` | **new** | Offline suite: zero pipeline runs, runs `merge_precision_recall` against fixture |
| `phase1-pablo/tests/runtime/test_tool_calls_timing.py` | **new** | Unit tests for ToolCall.duration_ms |
| `phase1-pablo/tests/eval/test_timing.py` | **new** | Unit tests for `record_stage`, `TimingLog.percentiles` |
| `phase1-pablo/tests/eval/test_assertions_timing.py` | **new** | Unit tests for `p95_below`, `avg_below` |
| `phase1-pablo/tests/eval/test_assertions_merge.py` | **new** | Unit tests for `merge_precision_recall` |
| `phase1-pablo/tests/eval/test_suite_assertions.py` | **new** | Integration test: a YAML with `suite_assertions:` parses and runs |

---

## Task 1: Add `duration_ms` field to `ToolCall`

**Files:**
- Modify: `phase1-pablo/src/decisionlab/runtime/tool_calls.py:30-41, 81-103`
- Test: `phase1-pablo/tests/runtime/test_tool_calls_timing.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# phase1-pablo/tests/runtime/test_tool_calls_timing.py
"""Timing fields on ToolCall — duration_ms threading through the
recorder. The duration is supplied by the dispatcher (which knows
when the handler started/ended); the recorder just stores it."""

from decisionlab.runtime.tool_calls import (
    ToolCall,
    record,
    start_recording,
)


def test_tool_call_duration_optional_default_none():
    tc = ToolCall(name="x", stage="research", args_hash="h", succeeded=True)
    assert tc.duration_ms is None


def test_tool_call_duration_set_via_record():
    log = start_recording()
    record("retrieve_knowledge", {"query": "q"}, succeeded=True, duration_ms=42.5)
    assert len(log) == 1
    assert log[0].duration_ms == 42.5


def test_record_without_duration_is_still_supported():
    """Backwards compatible: existing call sites pass no duration."""
    log = start_recording()
    record("retrieve_knowledge", {"query": "q"}, succeeded=True)
    assert log[0].duration_ms is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest phase1-pablo/tests/runtime/test_tool_calls_timing.py -v`
Expected: FAIL with `TypeError: ToolCall.__init__() got an unexpected keyword argument 'duration_ms'` or `record() got an unexpected keyword argument 'duration_ms'`.

- [ ] **Step 3: Implement the change**

In `phase1-pablo/src/decisionlab/runtime/tool_calls.py`, modify the dataclass and the `record()` function:

```python
@dataclass(frozen=True)
class ToolCall:
    name: str
    stage: str
    args_hash: str
    succeeded: bool
    details: dict | None = None
    # Wall time spent inside the dispatcher handler. None for legacy
    # call sites that don't measure (interactive CLI, tests).
    duration_ms: float | None = None


def record(
    name: str,
    args: object,
    succeeded: bool,
    *,
    duration_ms: float | None = None,
) -> None:
    log = _TOOL_CALLS_VAR.get()
    if log is None:
        return
    try:
        blob = json.dumps(args, sort_keys=True, default=str).encode()
    except (TypeError, ValueError):
        blob = repr(args).encode()
    args_hash = hashlib.md5(blob, usedforsecurity=False).hexdigest()[:12]
    log.append(
        ToolCall(
            name=name,
            stage=_STAGE_VAR.get(),
            args_hash=args_hash,
            succeeded=succeeded,
            duration_ms=duration_ms,
        )
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest phase1-pablo/tests/runtime/test_tool_calls_timing.py -v`
Expected: PASS, 3 passed.

- [ ] **Step 5: Confirm no existing tests broke**

Run: `uv run pytest phase1-pablo/tests/runtime/ phase1-pablo/tests/eval/test_runner.py -x`
Expected: PASS — `record(...)` callers don't pass `duration_ms` so they use the default `None`.

- [ ] **Step 6: Commit**

```bash
git add phase1-pablo/src/decisionlab/runtime/tool_calls.py phase1-pablo/tests/runtime/test_tool_calls_timing.py
git commit -m "feat[phase1-runtime]: add optional duration_ms to ToolCall"
```

---

## Task 2: Wire dispatcher to measure handler duration

**Files:**
- Modify: dispatcher in `phase1-pablo/src/decisionlab/runtime/` — find and modify the call site that invokes `record(...)` after a handler finishes.

- [ ] **Step 1: Locate the dispatcher**

Run: `grep -rn "tool_calls.record\b\|from decisionlab.runtime.tool_calls" phase1-pablo/src/decisionlab/runtime/`

Expected: at least one file (likely `dispatch.py` or `tools.py`) calls `tool_calls.record(name, args, succeeded=...)`.

- [ ] **Step 2: Write the failing test**

Create `phase1-pablo/tests/runtime/test_dispatcher_timing.py`. Replace `dispatch_tool` with the actual entry point name once located in Step 1.

```python
"""Dispatcher must measure handler runtime and stamp it on the
recorded ToolCall."""

import asyncio
import time

import pytest

from decisionlab.runtime.tool_calls import start_recording


@pytest.mark.asyncio
async def test_dispatcher_records_duration():
    from decisionlab.runtime.dispatch import dispatch_tool  # adjust import per Step 1

    async def slow_handler(args: dict) -> str:
        await asyncio.sleep(0.05)
        return "ok"

    log = start_recording()
    await dispatch_tool(
        name="slow",
        args={"x": 1},
        registry={"slow": slow_handler},
    )
    assert len(log) == 1
    assert log[0].duration_ms is not None
    assert log[0].duration_ms >= 50.0
    assert log[0].duration_ms < 200.0  # not crazy
```

- [ ] **Step 3: Run the test, verify it fails**

Run: `uv run pytest phase1-pablo/tests/runtime/test_dispatcher_timing.py -v`
Expected: FAIL with `assert None is not None` (current dispatcher doesn't pass duration).

- [ ] **Step 4: Implement timing in the dispatcher**

In the file located at Step 1, wrap the handler call with `time.monotonic_ns()`:

```python
import time
# ...

async def dispatch_tool(name: str, args: dict, registry: dict) -> str:
    handler = registry.get(name)
    if handler is None:
        tool_calls.record(name, args, succeeded=False, duration_ms=0.0)
        raise KeyError(f"unknown tool {name!r}")
    t0 = time.monotonic_ns()
    succeeded = False
    try:
        result = await handler(args)
        succeeded = True
        return result
    finally:
        duration_ms = (time.monotonic_ns() - t0) / 1_000_000
        tool_calls.record(name, args, succeeded=succeeded, duration_ms=duration_ms)
```

If the existing dispatcher already separates success/failure paths, keep both paths recording duration via a shared `finally`. **Do not** call `record()` twice on the success path.

- [ ] **Step 5: Run the test, verify it passes**

Run: `uv run pytest phase1-pablo/tests/runtime/test_dispatcher_timing.py -v`
Expected: PASS.

- [ ] **Step 6: Run runtime + eval test suites to confirm no regression**

Run: `uv run pytest phase1-pablo/tests/runtime/ phase1-pablo/tests/eval/ -x`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add phase1-pablo/src/decisionlab/runtime/ phase1-pablo/tests/runtime/test_dispatcher_timing.py
git commit -m "feat[phase1-runtime]: dispatcher measures handler duration"
```

---

## Task 3: Create `eval/timing.py` — TimingLog + record_stage

**Files:**
- Create: `phase1-pablo/src/decisionlab/eval/timing.py`
- Test: `phase1-pablo/tests/eval/test_timing.py`

- [ ] **Step 1: Write the failing test**

```python
# phase1-pablo/tests/eval/test_timing.py
"""TimingLog: stage timings + percentile aggregation over per-tool
durations harvested from a ToolCall log."""

import asyncio

import pytest

from decisionlab.eval.timing import (
    StageTiming,
    TimingLog,
    record_stage,
    start_timing,
)
from decisionlab.runtime.tool_calls import ToolCall


@pytest.mark.asyncio
async def test_record_stage_captures_duration():
    log = start_timing()
    async with record_stage("researcher"):
        await asyncio.sleep(0.02)
    assert len(log.stages) == 1
    assert log.stages[0].stage == "researcher"
    assert log.stages[0].duration_ms >= 20.0


def test_percentiles_from_tool_calls():
    """Aggregating ToolCall.duration_ms by tool name."""
    calls = (
        ToolCall(name="retrieve_knowledge", stage="r", args_hash="a", succeeded=True, duration_ms=100.0),
        ToolCall(name="retrieve_knowledge", stage="r", args_hash="b", succeeded=True, duration_ms=200.0),
        ToolCall(name="retrieve_knowledge", stage="r", args_hash="c", succeeded=True, duration_ms=300.0),
        ToolCall(name="web_search",         stage="r", args_hash="d", succeeded=True, duration_ms=50.0),
        ToolCall(name="web_search",         stage="r", args_hash="e", succeeded=True, duration_ms=None),
    )
    summary = TimingLog.summarize_tool_calls(calls)
    rk = summary["retrieve_knowledge"]
    assert rk["calls"] == 3
    assert rk["p50_ms"] == 200.0
    assert rk["p95_ms"] == pytest.approx(290.0, abs=15)
    assert rk["avg_ms"] == 200.0
    ws = summary["web_search"]
    assert ws["calls"] == 1   # the None duration is dropped from p50/p95 calc
    assert ws["p50_ms"] == 50.0


def test_empty_summary_returns_empty_dict():
    assert TimingLog.summarize_tool_calls(()) == {}


@pytest.mark.asyncio
async def test_record_stage_records_failure_path():
    """Stage timing must capture even when the body raises."""
    log = start_timing()
    with pytest.raises(RuntimeError):
        async with record_stage("formalizer"):
            await asyncio.sleep(0.005)
            raise RuntimeError("boom")
    assert len(log.stages) == 1
    assert log.stages[0].stage == "formalizer"
    assert log.stages[0].failed is True
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest phase1-pablo/tests/eval/test_timing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'decisionlab.eval.timing'`.

- [ ] **Step 3: Create `eval/timing.py`**

```python
# phase1-pablo/src/decisionlab/eval/timing.py
"""Timing collector for the eval harness.

Mirrors the ContextVar pattern used by ``runtime.tool_calls`` so the
runner can opt into recording per-stage durations without changing
non-eval code paths.

Per-tool durations are *not* stored separately — they come along on
``ToolCall.duration_ms`` (Task 2). ``TimingLog.summarize_tool_calls``
aggregates those into p50/p95/avg by tool name.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from statistics import mean

from decisionlab.runtime.tool_calls import ToolCall


@dataclass(frozen=True)
class StageTiming:
    stage: str
    duration_ms: float
    failed: bool


@dataclass
class TimingLog:
    stages: list[StageTiming] = field(default_factory=list)

    @staticmethod
    def summarize_tool_calls(
        calls: Iterable[ToolCall],
    ) -> dict[str, dict[str, float]]:
        """Compute calls / p50 / p95 / avg per tool name. Skips entries
        with ``duration_ms is None``."""
        buckets: dict[str, list[float]] = {}
        for c in calls:
            if c.duration_ms is None:
                continue
            buckets.setdefault(c.name, []).append(c.duration_ms)
        out: dict[str, dict[str, float]] = {}
        for name, durations in buckets.items():
            durations.sort()
            n = len(durations)
            p50 = durations[n // 2] if n else 0.0
            # Standard "nearest-rank" p95.
            p95_idx = max(0, min(n - 1, int(round(0.95 * n)) - 1))
            p95 = durations[p95_idx] if n else 0.0
            out[name] = {
                "calls": float(n),
                "p50_ms": float(p50),
                "p95_ms": float(p95),
                "avg_ms": float(mean(durations)),
            }
        return out


_TIMING_VAR: ContextVar[TimingLog | None] = ContextVar(
    "decisionlab_eval_timing", default=None
)


def start_timing() -> TimingLog:
    """Bind a fresh TimingLog to the current context. Idempotent across
    runs because each call replaces the binding."""
    log = TimingLog()
    _TIMING_VAR.set(log)
    return log


def current_timing() -> TimingLog | None:
    return _TIMING_VAR.get()


@asynccontextmanager
async def record_stage(name: str):
    """Async context manager: record duration of a stage body. No-op
    when no TimingLog is bound (production / interactive CLI)."""
    log = _TIMING_VAR.get()
    if log is None:
        yield
        return
    t0 = time.monotonic_ns()
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        elapsed_ms = (time.monotonic_ns() - t0) / 1_000_000
        log.stages.append(
            StageTiming(stage=name, duration_ms=elapsed_ms, failed=failed)
        )
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest phase1-pablo/tests/eval/test_timing.py -v`
Expected: PASS, 4 passed.

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/eval/timing.py phase1-pablo/tests/eval/test_timing.py
git commit -m "feat[phase1-eval]: TimingLog with stage durations and tool-call percentiles"
```

---

## Task 4: Wire `record_stage` into the Router

**Files:**
- Modify: `phase1-pablo/src/decisionlab/router.py` — find each `async def _run_*` stage method.

- [ ] **Step 1: Map the stage methods**

Run: `grep -nE "async def _run_(researcher|formalizer|reasoner|builder|canonicalize|memory)\b|async def _stage_" phase1-pablo/src/decisionlab/router.py`

Expected output: list of 4-6 stage methods (or one dispatcher that runs all). Note the actual method names — Step 4 below uses placeholders; substitute the real names you find.

- [ ] **Step 2: Write a failing integration test**

```python
# phase1-pablo/tests/eval/test_router_timing_integration.py
"""End-to-end: a Router run with a TimingLog bound captures one
StageTiming per stage that executed."""

import asyncio

import pytest

from decisionlab.eval.timing import current_timing, start_timing


@pytest.mark.asyncio
async def test_router_emits_stage_timings(monkeypatch, tmp_path):
    pytest.importorskip("anthropic")
    from decisionlab.router import Router, Stage
    from decisionlab.runtime.tool_calls import start_recording

    start_recording()
    log = start_timing()

    # Build a minimal router stub that runs only RESEARCH and exits.
    # Keep this test fast: monkeypatch the Researcher to a no-op.
    from decisionlab.agents import researcher as researcher_mod

    class _StubResearcher:
        def __init__(self, **_kw): ...
        async def run(self, *a, **kw):
            from decisionlab.agents.researcher import ResearchReport
            return ResearchReport(paradigms=[], summary="", deep_reports={})

    monkeypatch.setattr(researcher_mod, "Researcher", _StubResearcher)

    state = ...  # build PipelineState with topic="probe"
    router = Router(...)
    await router.run()

    stage_names = {s.stage for s in log.stages}
    # At minimum the researcher stage should have a timing entry.
    assert "researcher" in stage_names
```

> **Note for the engineer:** the `state = ...` and `router = Router(...)` placeholders are fixture wiring; fill them in by mirroring `phase1-pablo/tests/eval/test_runner_integration.py`. Substitute fixtures the existing tests already use.

- [ ] **Step 3: Run the test, verify it fails**

Run: `uv run pytest phase1-pablo/tests/eval/test_router_timing_integration.py -v`
Expected: FAIL — `assert 'researcher' in set()`.

- [ ] **Step 4: Wrap each stage method**

In `phase1-pablo/src/decisionlab/router.py`, import:

```python
from decisionlab.eval.timing import record_stage
```

For each stage method identified in Step 1, wrap the body:

```python
async def _run_researcher(self) -> None:
    async with record_stage("researcher"):
        # ... existing body unchanged
```

Repeat for `_run_formalizer`, `_run_reasoner`, `_run_builder`, `_run_canonicalize` (if it's a separate method), `_run_memory` (if separate). The exact set comes from Step 1.

- [ ] **Step 5: Run the integration test, verify it passes**

Run: `uv run pytest phase1-pablo/tests/eval/test_router_timing_integration.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full router/eval test suite to confirm no regression**

Run: `uv run pytest phase1-pablo/tests/ -x --ignore=phase1-pablo/tests/agents`

Expected: PASS. (Skipping `agents/` because those tests hit live LLMs by default; if your repo runs them with mocks, drop the `--ignore`.)

- [ ] **Step 7: Commit**

```bash
git add phase1-pablo/src/decisionlab/router.py phase1-pablo/tests/eval/test_router_timing_integration.py
git commit -m "feat[phase1-router]: wrap stage methods with eval timing collector"
```

---

## Task 5: Thread `TimingLog` onto `PipelineRunResult`

**Files:**
- Modify: `phase1-pablo/src/decisionlab/eval/models.py:17-47`
- Modify: `phase1-pablo/src/decisionlab/eval/runner.py:140-235`
- Test: `phase1-pablo/tests/eval/test_runner_timing.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# phase1-pablo/tests/eval/test_runner_timing.py
"""run_pipeline must populate result.timing with at least one stage."""

import pytest


@pytest.mark.asyncio
async def test_run_pipeline_populates_timing(monkeypatch, tmp_path, ...):
    """Reuse fixtures from test_runner_integration.py. The assertion is
    only on the presence of timing data, not its content."""
    from decisionlab.eval.runner import run_pipeline

    result = await run_pipeline(
        "Reinforcement learning in foraging environments",
        stages=("research",),
        # ... rest of args mirroring test_runner_integration.py
    )
    assert result.timing is not None
    assert len(result.timing.stages) >= 1
    assert any(s.stage == "researcher" for s in result.timing.stages)
```

> **Engineer note:** copy the fixture invocation exactly from `test_runner_integration.py` — same client mocks, same env_spec.

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest phase1-pablo/tests/eval/test_runner_timing.py -v`
Expected: FAIL — `AttributeError: 'PipelineRunResult' object has no attribute 'timing'`.

- [ ] **Step 3: Add the field to `PipelineRunResult`**

In `phase1-pablo/src/decisionlab/eval/models.py`, add the import and field:

```python
from decisionlab.eval.timing import TimingLog


@dataclass(frozen=True)
class PipelineRunResult:
    # ... existing fields unchanged ...
    started_at: str = ""
    timing: TimingLog | None = None  # populated by run_pipeline; None for legacy callers
```

- [ ] **Step 4: Populate it in `run_pipeline`**

In `phase1-pablo/src/decisionlab/eval/runner.py`, around line 165:

```python
from decisionlab.eval.timing import start_timing
# ...

started_at_iso = datetime.now(UTC).isoformat()
tool_call_log = _start_tool_call_recording()
timing_log = start_timing()  # NEW

await _create_run_row(rid, topic)
# ... rest unchanged ...
```

And at the return site (line ~220):

```python
return PipelineRunResult(
    # ... existing fields ...
    started_at=started_at_iso,
    timing=timing_log,
)
```

- [ ] **Step 5: Run the test, verify it passes**

Run: `uv run pytest phase1-pablo/tests/eval/test_runner_timing.py -v`
Expected: PASS.

- [ ] **Step 6: Confirm no regression in existing runner tests**

Run: `uv run pytest phase1-pablo/tests/eval/test_runner.py phase1-pablo/tests/eval/test_runner_integration.py -x`
Expected: PASS — `timing` defaults to `None` for any test that constructs `PipelineRunResult` directly.

- [ ] **Step 7: Commit**

```bash
git add phase1-pablo/src/decisionlab/eval/models.py phase1-pablo/src/decisionlab/eval/runner.py phase1-pablo/tests/eval/test_runner_timing.py
git commit -m "feat[phase1-eval]: thread TimingLog onto PipelineRunResult"
```

---

## Task 6: Add `SuiteAssertionContext` and `register_suite`

**Files:**
- Modify: `phase1-pablo/src/decisionlab/eval/assertions.py:29-95`

- [ ] **Step 1: Write the failing test**

```python
# phase1-pablo/tests/eval/test_suite_assertions.py
"""Suite-level predicate registry — predicates that need cross-topic
context to evaluate."""

import pytest

from decisionlab.eval.assertions import (
    AssertionOutcome,
    SuiteAssertionContext,
    register_suite,
    run_suite_assertion,
)


@pytest.mark.asyncio
async def test_register_and_dispatch_suite_predicate():
    @register_suite("dummy_count")
    async def _dummy(ctx: SuiteAssertionContext, args) -> AssertionOutcome:
        n = args["n"]
        return AssertionOutcome(
            name="dummy_count",
            passed=len(ctx.topic_results) >= n,
            detail=f"topics={len(ctx.topic_results)}",
        )

    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(),
        pre_stats=None,
        post_stats=None,
    )
    out = await run_suite_assertion({"dummy_count": {"n": 0}}, ctx)
    assert out.passed
    assert "topics=0" in out.detail


@pytest.mark.asyncio
async def test_unknown_suite_predicate_fails_cleanly():
    ctx = SuiteAssertionContext(
        suite=None, topic_results=(), pre_stats=None, post_stats=None
    )
    out = await run_suite_assertion({"never_registered": {}}, ctx)
    assert not out.passed
    assert "unknown" in out.detail.lower()
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest phase1-pablo/tests/eval/test_suite_assertions.py -v`
Expected: FAIL with `ImportError: cannot import name 'SuiteAssertionContext'`.

- [ ] **Step 3: Implement the suite-level registry**

In `phase1-pablo/src/decisionlab/eval/assertions.py`, after the existing `_REGISTRY`:

```python
from decisionlab.eval.kgadmin import KGStats  # type: ignore[attr-defined]

# Forward-declare types used only as annotations.
if TYPE_CHECKING:
    from decisionlab.eval.suite import SuiteSpec, TopicResult


@dataclass(frozen=True)
class SuiteAssertionContext:
    """What a suite-level predicate can read: full topic-result tuple,
    KG stats before/after, and the suite spec itself for cross-references."""

    suite: "SuiteSpec | None"
    topic_results: tuple["TopicResult", ...]
    pre_stats: KGStats | None
    post_stats: KGStats | None


SuitePredicateFn = Callable[
    [SuiteAssertionContext, Any], Awaitable[AssertionOutcome]
]
_SUITE_REGISTRY: dict[str, SuitePredicateFn] = {}


def register_suite(name: str) -> Callable[[SuitePredicateFn], SuitePredicateFn]:
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
                f"unknown suite predicate {name!r}; "
                f"valid: {suite_predicate_names()}"
            ),
        )
    try:
        return await fn(ctx, args)
    except Exception as exc:
        return AssertionOutcome(
            name=name,
            passed=False,
            detail=f"suite predicate {name!r} raised: {exc}",
        )
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest phase1-pablo/tests/eval/test_suite_assertions.py -v`
Expected: PASS, 2 passed.

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/eval/assertions.py phase1-pablo/tests/eval/test_suite_assertions.py
git commit -m "feat[phase1-eval]: SuiteAssertionContext + register_suite registry"
```

---

## Task 7: Add `p95_below` and `avg_below` predicates

**Files:**
- Modify: `phase1-pablo/src/decisionlab/eval/assertions.py`
- Test: `phase1-pablo/tests/eval/test_assertions_timing.py`

- [ ] **Step 1: Write the failing test**

```python
# phase1-pablo/tests/eval/test_assertions_timing.py
"""Timing predicates: aggregate per-tool p95 and per-stage average
across a topic_results tuple."""

import pytest

from decisionlab.eval.assertions import (
    SuiteAssertionContext,
    run_suite_assertion,
)
from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.suite import TopicResult
from decisionlab.eval.timing import StageTiming, TimingLog
from decisionlab.runtime.tool_calls import ToolCall


def _topic_result(durations_ms: list[float], stages: list[tuple[str, float]]):
    timing = TimingLog(
        stages=[StageTiming(s, d, failed=False) for s, d in stages]
    )
    calls = tuple(
        ToolCall(
            name="retrieve_knowledge",
            stage="researcher",
            args_hash=str(i),
            succeeded=True,
            duration_ms=d,
        )
        for i, d in enumerate(durations_ms)
    )
    run = PipelineRunResult(
        run_id=f"r{len(durations_ms)}",
        topic="probe",
        stages_run=("research",),
        tool_call_log=calls,
        timing=timing,
    )
    return TopicResult(topic=run.topic, run=run, assertions={})


@pytest.mark.asyncio
async def test_p95_below_passes_when_under_threshold():
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(
            _topic_result([100, 150, 200, 1000, 2400], [("researcher", 5000)]),
        ),
        pre_stats=None,
        post_stats=None,
    )
    out = await run_suite_assertion(
        {"p95_below": {"tool": "retrieve_knowledge", "p95_ms": 2500}}, ctx
    )
    assert out.passed, out.detail


@pytest.mark.asyncio
async def test_p95_below_fails_when_over():
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(
            _topic_result([100, 200, 300, 1000, 5000], [("researcher", 1000)]),
        ),
        pre_stats=None,
        post_stats=None,
    )
    out = await run_suite_assertion(
        {"p95_below": {"tool": "retrieve_knowledge", "p95_ms": 2500}}, ctx
    )
    assert not out.passed
    assert "p95" in out.detail.lower()


@pytest.mark.asyncio
async def test_avg_below_passes_for_stage():
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(
            _topic_result([], [("canonicalize", 5000)]),
            _topic_result([], [("canonicalize", 7000)]),
        ),
        pre_stats=None,
        post_stats=None,
    )
    out = await run_suite_assertion(
        {"avg_below": {"stage": "canonicalize", "avg_ms": 8000}}, ctx
    )
    assert out.passed


@pytest.mark.asyncio
async def test_avg_below_no_data_fails_visibly():
    ctx = SuiteAssertionContext(
        suite=None, topic_results=(), pre_stats=None, post_stats=None
    )
    out = await run_suite_assertion(
        {"avg_below": {"stage": "canonicalize", "avg_ms": 8000}}, ctx
    )
    assert not out.passed
    assert "no data" in out.detail.lower()
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest phase1-pablo/tests/eval/test_assertions_timing.py -v`
Expected: FAIL — `unknown suite predicate 'p95_below'`.

- [ ] **Step 3: Implement the predicates**

Append to `phase1-pablo/src/decisionlab/eval/assertions.py`:

```python
@register_suite("p95_below")
async def _p95_below(ctx: SuiteAssertionContext, args) -> AssertionOutcome:
    """Aggregate ToolCall.duration_ms across all topics and assert the
    per-tool p95 is below the configured threshold.

    args: {"tool": "retrieve_knowledge", "p95_ms": 2500}
    """
    tool = args["tool"]
    threshold = float(args["p95_ms"])
    all_calls = []
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
        detail=f"{stage} avg={avg:.0f}ms (n={len(durations)}) threshold={threshold:.0f}ms",
    )
```

Add the `TimingLog` import at the top of `assertions.py`:

```python
from decisionlab.eval.timing import TimingLog
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest phase1-pablo/tests/eval/test_assertions_timing.py -v`
Expected: PASS, 4 passed.

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/eval/assertions.py phase1-pablo/tests/eval/test_assertions_timing.py
git commit -m "feat[phase1-eval]: p95_below + avg_below suite predicates"
```

---

## Task 8: Add `merge_precision_recall` predicate

**Files:**
- Modify: `phase1-pablo/src/decisionlab/eval/assertions.py`
- Test: `phase1-pablo/tests/eval/test_assertions_merge.py`

- [ ] **Step 1: Inspect the fixture format**

Run: `head -40 phase1-pablo/evals/fixtures/canonicalize-pairs.json`

Confirm the structure (expected: a JSON array of `{label, candidate, existing, should_merge}` triples per the audit). If the schema differs, adjust the predicate code in Step 3.

- [ ] **Step 2: Write the failing test**

```python
# phase1-pablo/tests/eval/test_assertions_merge.py
"""merge_precision_recall: load 18-pair fixture, call _verify_merge per
pair, compute precision/recall/F1 vs labels."""

import json
from unittest.mock import AsyncMock

import pytest

from decisionlab.eval.assertions import (
    SuiteAssertionContext,
    run_suite_assertion,
)


@pytest.fixture()
def fake_fixture(tmp_path):
    pairs = [
        {"label": "Paradigm", "candidate": "Q-learning", "existing": "reinforcement-learning", "should_merge": True},
        {"label": "Paradigm", "candidate": "DDM",        "existing": "drift-diffusion-model",  "should_merge": True},
        {"label": "Paradigm", "candidate": "DDM",        "existing": "prospect-theory",        "should_merge": False},
        {"label": "Variable", "candidate": "reward",     "existing": "value",                  "should_merge": False},
    ]
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps(pairs))
    return path


@pytest.mark.asyncio
async def test_merge_pr_perfect_score(monkeypatch, fake_fixture):
    """Verifier always returns the labelled answer => precision=recall=1."""
    from decisionlab.eval import assertions as A

    # Stub _verify_merge to return whatever the label says.
    async def fake_verify(*, label, candidate_text, existing_text, similarity, client):
        # Look up the pair in the fixture by text content.
        from decisionlab.canonicalize import _MergeVerification
        pairs = json.loads(fake_fixture.read_text())
        for p in pairs:
            if p["candidate"] == candidate_text and p["existing"] == existing_text:
                return _MergeVerification(merge=p["should_merge"], reason="oracle")
        raise AssertionError(f"unknown pair: {candidate_text} / {existing_text}")

    monkeypatch.setattr("decisionlab.canonicalize._verify_merge", fake_verify)

    ctx = SuiteAssertionContext(
        suite=None, topic_results=(), pre_stats=None, post_stats=None
    )
    out = await run_suite_assertion(
        {
            "merge_precision_recall": {
                "fixture": str(fake_fixture),
                "min_precision": 0.95,
                "min_recall": 0.90,
            }
        },
        ctx,
    )
    assert out.passed, out.detail
    assert "precision=1.000" in out.detail
    assert "recall=1.000" in out.detail


@pytest.mark.asyncio
async def test_merge_pr_low_precision_fails(monkeypatch, fake_fixture):
    """Verifier always says merge => 2 TP, 2 FP => precision=0.5."""
    from decisionlab.eval import assertions as A
    from decisionlab.canonicalize import _MergeVerification

    async def always_merge(**_kw):
        return _MergeVerification(merge=True, reason="always")

    monkeypatch.setattr("decisionlab.canonicalize._verify_merge", always_merge)

    ctx = SuiteAssertionContext(
        suite=None, topic_results=(), pre_stats=None, post_stats=None
    )
    out = await run_suite_assertion(
        {
            "merge_precision_recall": {
                "fixture": str(fake_fixture),
                "min_precision": 0.95,
                "min_recall": 0.90,
            }
        },
        ctx,
    )
    assert not out.passed
    assert "precision=0.500" in out.detail


@pytest.mark.asyncio
async def test_merge_pr_missing_fixture_fails_cleanly():
    ctx = SuiteAssertionContext(
        suite=None, topic_results=(), pre_stats=None, post_stats=None
    )
    out = await run_suite_assertion(
        {
            "merge_precision_recall": {
                "fixture": "/nonexistent.json",
                "min_precision": 0.95,
                "min_recall": 0.90,
            }
        },
        ctx,
    )
    assert not out.passed
    assert "fixture" in out.detail.lower()
```

- [ ] **Step 3: Run the test, verify it fails**

Run: `uv run pytest phase1-pablo/tests/eval/test_assertions_merge.py -v`
Expected: FAIL — `unknown suite predicate 'merge_precision_recall'`.

- [ ] **Step 4: Implement the predicate**

Append to `phase1-pablo/src/decisionlab/eval/assertions.py`:

```python
import json as _json
from pathlib import Path as _Path


@register_suite("merge_precision_recall")
async def _merge_precision_recall(
    ctx: SuiteAssertionContext, args
) -> AssertionOutcome:
    """Run canonicalize._verify_merge over a labelled fixture and compute
    precision/recall/F1.

    args: {fixture: path, min_precision: 0.95, min_recall: 0.90}

    Cost: ~$0.05 per pair (one Sonnet call). 18-pair fixture ~ $1.
    """
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
        pairs = _json.loads(fixture_path.read_text())
    except _json.JSONDecodeError as exc:
        return AssertionOutcome(
            name="merge_precision_recall",
            passed=False,
            detail=f"fixture not valid JSON: {exc}",
        )
    if not isinstance(pairs, list) or not pairs:
        return AssertionOutcome(
            name="merge_precision_recall",
            passed=False,
            detail="fixture must be a non-empty list of pairs",
        )

    # Late import to avoid a heavy dep at module load time.
    from anthropic import AsyncAnthropic

    from decisionlab.canonicalize import _verify_merge

    client = AsyncAnthropic()

    tp = fp = fn = tn = 0
    for p in pairs:
        decision = await _verify_merge(
            label=p["label"],
            candidate_text=p["candidate"],
            existing_text=p["existing"],
            # similarity is supplied to the prompt; we don't have one
            # here without re-embedding, so pass 0.0 — the verifier's
            # job is to make the call from the texts themselves.
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
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
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
```

- [ ] **Step 5: Run the test, verify it passes**

Run: `uv run pytest phase1-pablo/tests/eval/test_assertions_merge.py -v`
Expected: PASS, 3 passed.

- [ ] **Step 6: Commit**

```bash
git add phase1-pablo/src/decisionlab/eval/assertions.py phase1-pablo/tests/eval/test_assertions_merge.py
git commit -m "feat[phase1-eval]: merge_precision_recall suite predicate against fixture"
```

---

## Task 9: Parse `suite_assertions:` from YAML and run them

**Files:**
- Modify: `phase1-pablo/src/decisionlab/eval/suite.py:51-123, 232-350`
- Test: extend `phase1-pablo/tests/eval/test_suite_assertions.py`

- [ ] **Step 1: Extend the test to cover end-to-end parsing**

Append to `phase1-pablo/tests/eval/test_suite_assertions.py`:

```python
@pytest.mark.asyncio
async def test_suite_yaml_runs_suite_assertions(tmp_path, monkeypatch):
    """A suite YAML with a top-level ``suite_assertions:`` block runs
    those predicates after the topic loop."""
    from decisionlab.eval.assertions import register_suite, AssertionOutcome
    from decisionlab.eval.suite import SuiteSpec, run_suite

    @register_suite("always_pass")
    async def _ap(ctx, args) -> AssertionOutcome:
        return AssertionOutcome(name="always_pass", passed=True, detail="ok")

    yaml_text = """
name: probe
stages: []
topics:
  - text: probe-only
suite_assertions:
  - always_pass: {}
"""
    path = tmp_path / "probe.yaml"
    path.write_text(yaml_text)
    spec = SuiteSpec.from_yaml(path)
    assert spec.suite_assertions == ({"always_pass": {}},)
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest phase1-pablo/tests/eval/test_suite_assertions.py::test_suite_yaml_runs_suite_assertions -v`
Expected: FAIL — `AttributeError: 'SuiteSpec' object has no attribute 'suite_assertions'`.

- [ ] **Step 3: Add the field to SuiteSpec and parse it**

Modify `SuiteSpec` in `phase1-pablo/src/decisionlab/eval/suite.py:59-69`:

```python
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
```

In `from_yaml` after parsing topics, before `return cls(...)`:

```python
raw_suite_assertions = raw.get("suite_assertions") or []
if not isinstance(raw_suite_assertions, list):
    raise ValueError(
        f"suite {raw.get('name', '?')!r}: suite_assertions must be a list"
    )
suite_assertions = tuple(raw_suite_assertions)
```

Pass `suite_assertions=suite_assertions` into the `cls(...)` constructor call.

Now allow `stages: []` (empty list) — modify the stages parser:

```python
stages = tuple(_parse_stages(raw.get("stages") or []))
```

(was `raw.get("stages") or ["research"]` — change the default to `[]` so suites declaring no stages stay empty).

Also relax `_validate_stages` in runner.py if it rejects `()`. If `stages_run` is empty in `run_pipeline`, we want it to be a no-op pipeline (just so suite assertions can run).

In `phase1-pablo/src/decisionlab/eval/runner.py:151`:

```python
stages_run = _validate_stages(stages)
if not stages_run:
    # No stages requested — useful for offline-only suites that just
    # run suite_assertions (e.g. merge_precision_recall against a fixture).
    return PipelineRunResult(
        run_id=run_id or str(uuid.uuid4()),
        topic=topic,
        stages_run=(),
        started_at=datetime.now(UTC).isoformat(),
        timing=TimingLog(),
    )
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest phase1-pablo/tests/eval/test_suite_assertions.py::test_suite_yaml_runs_suite_assertions -v`
Expected: PASS.

- [ ] **Step 5: Run the suite_assertions in `run_suite`**

Add to `SuiteResult` in `phase1-pablo/src/decisionlab/eval/suite.py:161-181`:

```python
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
    suite_assertions: tuple[AssertionOutcome, ...] = ()  # NEW

    @property
    def all_passed(self) -> bool:
        return (
            self.error is None
            and not self.budget_exhausted
            and all(t.all_passed for t in self.topic_results)
            and all(o.passed for o in self.suite_assertions)
        )
```

In `run_suite` (line ~333), just before computing `duration_ms`:

```python
# Run suite-level assertions.
from decisionlab.eval.assertions import (
    SuiteAssertionContext,
    run_suite_assertion,
)
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
```

And include `suite_assertions=tuple(suite_outcomes)` in the `SuiteResult(...)` return.

- [ ] **Step 6: Add an end-to-end test**

Append to `phase1-pablo/tests/eval/test_suite_assertions.py`:

```python
@pytest.mark.asyncio
async def test_run_suite_executes_suite_assertions(tmp_path, monkeypatch):
    """run_suite collects outcomes from suite_assertions onto SuiteResult."""
    from anthropic import AsyncAnthropic

    from decisionlab.eval.assertions import register_suite, AssertionOutcome
    from decisionlab.eval.suite import SuiteSpec, run_suite

    @register_suite("hits_n")
    async def _hn(ctx, args) -> AssertionOutcome:
        n = args["n"]
        return AssertionOutcome(
            name="hits_n",
            passed=len(ctx.topic_results) == n,
            detail=f"n={len(ctx.topic_results)}",
        )

    yaml_text = """
name: probe-stages-empty
stages: []
topics:
  - text: probe-1
  - text: probe-2
suite_assertions:
  - hits_n: { n: 2 }
"""
    path = tmp_path / "probe.yaml"
    path.write_text(yaml_text)
    spec = SuiteSpec.from_yaml(path)

    class _NullSearch:
        async def search(self, q: str): return []

    result = await run_suite(
        spec,
        client=AsyncAnthropic(),
        search=_NullSearch(),
        skip_kg_ops=True,
    )
    assert len(result.suite_assertions) == 1
    assert result.suite_assertions[0].name == "hits_n"
    assert result.suite_assertions[0].passed
```

- [ ] **Step 7: Run the new test**

Run: `uv run pytest phase1-pablo/tests/eval/test_suite_assertions.py -v`
Expected: PASS, 4 passed total.

- [ ] **Step 8: Commit**

```bash
git add phase1-pablo/src/decisionlab/eval/suite.py phase1-pablo/src/decisionlab/eval/runner.py phase1-pablo/tests/eval/test_suite_assertions.py
git commit -m "feat[phase1-eval]: parse and execute suite_assertions in run_suite"
```

---

## Task 10: Render timing + suite_assertions in reports

**Files:**
- Modify: `phase1-pablo/src/decisionlab/eval/report.py:12-83, 86-end`
- Test: extend `phase1-pablo/tests/eval/test_report.py`

- [ ] **Step 1: Read existing report tests to copy fixture style**

Run: `uv run pytest phase1-pablo/tests/eval/test_report.py -v --collect-only | head -30`

Note the fixture builders used (e.g. how `SuiteResult` is constructed in tests).

- [ ] **Step 2: Write failing tests**

Append to `phase1-pablo/tests/eval/test_report.py`:

```python
def test_report_md_includes_timing_section(make_suite_result):
    from decisionlab.eval.report import render_markdown
    from decisionlab.eval.timing import StageTiming, TimingLog
    from decisionlab.runtime.tool_calls import ToolCall

    timing = TimingLog(
        stages=[
            StageTiming(stage="researcher", duration_ms=1234.5, failed=False),
            StageTiming(stage="canonicalize", duration_ms=678.9, failed=False),
        ]
    )
    calls = (
        ToolCall(name="retrieve_knowledge", stage="r", args_hash="x",
                 succeeded=True, duration_ms=420.0),
    )
    sr = make_suite_result(timing=timing, tool_calls=calls)
    md = render_markdown(sr)
    assert "## Timing" in md
    assert "researcher" in md
    assert "1235" in md or "1234" in md  # ms formatting tolerance
    assert "retrieve_knowledge" in md


def test_report_json_includes_timing_and_suite_assertions(make_suite_result):
    import json
    from decisionlab.eval.assertions import AssertionOutcome
    from decisionlab.eval.report import render_json
    from decisionlab.eval.timing import StageTiming, TimingLog
    from decisionlab.runtime.tool_calls import ToolCall

    timing = TimingLog(stages=[StageTiming("researcher", 1000.0, False)])
    calls = (
        ToolCall(name="retrieve_knowledge", stage="r", args_hash="x",
                 succeeded=True, duration_ms=300.0),
    )
    sr = make_suite_result(
        timing=timing,
        tool_calls=calls,
        suite_assertions=(
            AssertionOutcome(name="merge_precision_recall", passed=True,
                             detail="precision=1.000 recall=1.000"),
        ),
    )
    payload = json.loads(render_json(sr))
    assert "suite_assertions" in payload
    assert payload["suite_assertions"][0]["name"] == "merge_precision_recall"
    assert payload["topic_results"][0]["timing"]["stages"][0]["stage"] == "researcher"
    assert payload["topic_results"][0]["tool_call_summary"]["retrieve_knowledge"]["calls"] == 1
```

The `make_suite_result` fixture must be added to `tests/eval/conftest.py` (or extended if it exists). It builds a one-topic SuiteResult with optional timing/tool_calls/suite_assertions kwargs. Engineer: copy whichever pattern existing tests use.

- [ ] **Step 3: Run the tests, verify they fail**

Run: `uv run pytest phase1-pablo/tests/eval/test_report.py -v -k "timing or suite_assertions"`
Expected: FAIL — sections missing from report output.

- [ ] **Step 4: Update `render_markdown`**

In `phase1-pablo/src/decisionlab/eval/report.py`, after the per-topic loop (line ~82) and before `return "\n".join(lines)`:

```python
# Suite-level assertions section
if result.suite_assertions:
    lines.append("## Suite assertions")
    lines.append("")
    lines.append("| Predicate | Result | Detail |")
    lines.append("|---|:-:|---|")
    for o in result.suite_assertions:
        mark = "✓" if o.passed else "✗"
        detail = o.detail.replace("|", "\\|")
        lines.append(f"| {o.name} | {mark} | {detail} |")
    lines.append("")

# Timing section (aggregated across topics)
all_calls: list = []
all_stage_ms: dict[str, list[float]] = {}
for tr in result.topic_results:
    all_calls.extend(tr.run.tool_call_log)
    if tr.run.timing is None:
        continue
    for st in tr.run.timing.stages:
        all_stage_ms.setdefault(st.stage, []).append(st.duration_ms)

if all_calls or all_stage_ms:
    lines.append("## Timing")
    lines.append("")
if all_stage_ms:
    lines.append("**Stages (avg ms across topics)**:")
    lines.append("")
    lines.append("| Stage | n | avg ms |")
    lines.append("|---|---:|---:|")
    for stage_name, durs in sorted(all_stage_ms.items()):
        avg = sum(durs) / len(durs)
        lines.append(f"| {stage_name} | {len(durs)} | {avg:.0f} |")
    lines.append("")
if all_calls:
    from decisionlab.eval.timing import TimingLog
    summary = TimingLog.summarize_tool_calls(all_calls)
    if summary:
        lines.append("**Tool calls**:")
        lines.append("")
        lines.append("| Tool | Calls | p50 ms | p95 ms | avg ms |")
        lines.append("|---|---:|---:|---:|---:|")
        for tool, s in sorted(summary.items()):
            lines.append(
                f"| {tool} | {int(s['calls'])} | "
                f"{s['p50_ms']:.0f} | {s['p95_ms']:.0f} | {s['avg_ms']:.0f} |"
            )
        lines.append("")
```

- [ ] **Step 5: Update `render_json`**

In `phase1-pablo/src/decisionlab/eval/report.py:86`, find the function body and add:

```python
def render_json(result: SuiteResult) -> str:
    spec = result.suite

    def _kgs(s):
        # ... existing helper unchanged
        ...

    def _tr(tr):
        # ... existing topic-result serializer ...
        # Inside the dict that gets returned for each topic, add:
        timing_payload = None
        if tr.run.timing is not None:
            timing_payload = {
                "stages": [asdict(s) for s in tr.run.timing.stages],
            }
        tool_call_summary = TimingLog.summarize_tool_calls(tr.run.tool_call_log)
        return {
            # ... existing fields ...
            "timing": timing_payload,
            "tool_call_summary": tool_call_summary,
        }

    payload = {
        # ... existing top-level fields ...
        "suite_assertions": [
            asdict(o) for o in result.suite_assertions
        ],
    }
    return json.dumps(payload, indent=2)
```

Add the import at the top:

```python
from decisionlab.eval.timing import TimingLog
```

- [ ] **Step 6: Run the tests, verify they pass**

Run: `uv run pytest phase1-pablo/tests/eval/test_report.py -v`
Expected: PASS — all existing report tests + the two new ones.

- [ ] **Step 7: Commit**

```bash
git add phase1-pablo/src/decisionlab/eval/report.py phase1-pablo/tests/eval/test_report.py phase1-pablo/tests/eval/conftest.py
git commit -m "feat[phase1-eval]: render timing + suite_assertions in MD/JSON reports"
```

---

## Task 11: Create `merge-quality.yaml` suite

**Files:**
- Create: `phase1-pablo/evals/suites/merge-quality.yaml`

- [ ] **Step 1: Write the suite YAML**

```yaml
# phase1-pablo/evals/suites/merge-quality.yaml
# Offline merge-quality regression — the tight loop for canonicalize-tau
# tuning. Runs no pipeline; calls _verify_merge once per fixture pair.
#
# Pre-condition: none (offline).
# Cost: ~$0.05/pair × 18 pairs ≈ $0.90.

name: merge-quality
stages: []
reset_kg_before: false

# One synthetic topic so SuiteSpec.topics is non-empty (the runner skips
# pipeline work when stages is empty, so topic.text is just a label).
topics:
  - text: "merge-quality-fixture"

suite_assertions:
  - merge_precision_recall:
      fixture: evals/fixtures/canonicalize-pairs.json
      min_precision: 0.95
      min_recall:    0.90

budget:
  max_usd_total: 1.50
```

- [ ] **Step 2: Verify the fixture exists**

Run: `wc -l phase1-pablo/evals/fixtures/canonicalize-pairs.json && head -30 phase1-pablo/evals/fixtures/canonicalize-pairs.json`

Confirm the file has the expected `[ {...}, {...} ]` shape.

- [ ] **Step 3: Dry-run via the suite parser to catch YAML errors**

Run:
```bash
uv run python -c "
from pathlib import Path
from decisionlab.eval.suite import SuiteSpec
spec = SuiteSpec.from_yaml(Path('phase1-pablo/evals/suites/merge-quality.yaml'))
print('topics:', len(spec.topics))
print('suite_assertions:', spec.suite_assertions)
print('stages:', spec.stages)
"
```

Expected output: `topics: 1`, `suite_assertions: ({'merge_precision_recall': {...}},)`, `stages: ()`.

- [ ] **Step 4: Commit**

```bash
git add phase1-pablo/evals/suites/merge-quality.yaml
git commit -m "feat[phase1-eval]: merge-quality.yaml offline suite"
```

---

## Task 12: Run the merge-quality baseline + commit numbers

**Files:**
- Create: `phase1-pablo/evals/reports/2026-05-08-baseline-merge-quality/` (output of the run)

- [ ] **Step 1: Confirm `.env` is loaded for `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY`**

Run: `grep -E "ANTHROPIC_API_KEY|OPENROUTER_API_KEY" phase1-pablo/.env | wc -l`
Expected: ≥ 1 (the suite calls Sonnet 4.6 via `_verify_merge`).

- [ ] **Step 2: Run the suite**

Run:
```bash
cd phase1-pablo
uv run python -m decisionlab.cli eval run evals/suites/merge-quality.yaml
```

Expected: completes in <2 minutes, produces `evals/reports/<auto>/report.md` and `report.json`. The MD report shows a `## Suite assertions` table with one row (`merge_precision_recall`).

If the existing CLI subcommand differs, locate it:
`grep -n "argparse\|click" phase1-pablo/src/decisionlab/cli.py | head -5`
and use whatever invocation the smoke suite uses (`evals/suites/smoke.yaml` is the reference).

- [ ] **Step 3: Sanity-check the report**

Run:
```bash
ls phase1-pablo/evals/reports/ | tail -3
LAST=$(ls -t phase1-pablo/evals/reports/ | head -1)
cat "phase1-pablo/evals/reports/${LAST}/report.md"
```

Expected: a report with `Overall: PASS` or `FAIL` (depending on whether current canonicalizer hits ≥0.95 precision / ≥0.90 recall on the 18-pair fixture). Note the `precision=`, `recall=`, `f1=` numbers — these are your **baseline**.

- [ ] **Step 4: Move/rename the baseline directory for permanence**

```bash
LAST=$(ls -t phase1-pablo/evals/reports/ | head -1)
mv "phase1-pablo/evals/reports/${LAST}" phase1-pablo/evals/reports/2026-05-08-baseline-merge-quality
```

- [ ] **Step 5: Append baseline numbers to the spec doc**

Open `phase1-pablo/docs/superpowers/specs/2026-05-08-memory-system-accuracy-refactor-design.md`, find the **Success criteria (final)** table, and replace the `unmeasured` cells in the **Merge precision** and **Merge recall** rows with the actual baseline values from Step 3:

```markdown
| Merge precision (`merge-quality.yaml`) | <baseline_p:.3f> | ≥ 0.95 |
| Merge recall  (`merge-quality.yaml`)   | <baseline_r:.3f> | ≥ 0.90 |
```

- [ ] **Step 6: Commit**

```bash
git add phase1-pablo/evals/reports/2026-05-08-baseline-merge-quality/ phase1-pablo/docs/superpowers/specs/2026-05-08-memory-system-accuracy-refactor-design.md
git commit -m "feat[phase1-eval]: baseline merge-quality report 2026-05-08"
```

---

## Task 13: Lint, typecheck, and final regression sweep

- [ ] **Step 1: Run the project formatter check**

Run: `cd phase1-pablo && uv run ruff format --check .`
Expected: no diffs. If diffs exist, run `uv run ruff format .`, review, and amend the most recent commit (only if it's the formatting fix; otherwise commit separately).

- [ ] **Step 2: Run the linter**

Run: `cd phase1-pablo && uv run ruff check .`
Expected: no errors.

- [ ] **Step 3: Run the type checker (if configured)**

Run: `cd phase1-pablo && uv run mypy src/decisionlab/eval src/decisionlab/runtime 2>&1 | tail -30`
Expected: no errors in the touched paths. Pre-existing errors in untouched modules are OK.

- [ ] **Step 4: Run the full test suite for affected packages**

Run:
```bash
cd phase1-pablo
uv run pytest tests/runtime tests/eval -x
```

Expected: all PASS.

- [ ] **Step 5: Commit any formatter fixes**

If the formatter changed anything, commit it with:

```bash
git add -A
git commit -m "chore[phase1-eval]: ruff format pass on Phase 0 additions"
```

---

## Self-Review

**Spec coverage check:**

| Spec deliverable (Phase 0) | Implemented in |
|----------------------------|----------------|
| D6a `TimingLog` hooks | Tasks 3, 4 |
| D6b report fields (`timing` per topic) | Task 10 |
| D6c `p95_below`, `avg_below` predicates | Task 7 |
| D2 `merge_precision_recall` predicate | Task 8 |
| D5 `merge-quality.yaml` suite | Task 11 |
| Baseline run + recorded numbers | Task 12 |
| `suite_assertions:` plumbing | Task 9 |

All Phase 0 spec items have a task. Phase 1 (cheap Track A wins — A2/A3) and later phases are covered by separate plans, to be authored after Phase 0 baseline numbers exist.

**Placeholder check:** No "TBD", "implement later", or "fill in details". Two engineer-direction notes ("substitute fixture wiring" in Tasks 4-5, "locate the dispatcher" in Task 2) are intentional — those are codebase-specific lookups the engineer must do.

**Type consistency:** `TimingLog`, `StageTiming`, `ToolCall.duration_ms`, `SuiteAssertionContext` names are stable across all tasks. `register_suite` decorator name matches across Tasks 6, 7, 8, and the test in Task 9. `merge_precision_recall` predicate name matches the spec verbatim and the YAML in Task 11.


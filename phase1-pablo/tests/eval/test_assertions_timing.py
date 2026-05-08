"""Timing predicates: aggregate per-tool p95 and per-stage average
across a topic_results tuple."""

from __future__ import annotations

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
        stages_run=(),
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

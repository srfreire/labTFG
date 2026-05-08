"""TimingLog: stage timings + percentile aggregation over per-tool
durations harvested from a ToolCall log."""

import asyncio

import pytest

from decisionlab.eval.timing import (
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

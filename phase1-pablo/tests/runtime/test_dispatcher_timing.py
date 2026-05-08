"""Dispatcher must measure handler runtime and stamp it on the
recorded ToolCall."""

import asyncio

import pytest

from decisionlab.runtime.dispatcher import dispatch_tools
from decisionlab.runtime.tool_calls import start_recording


class FakeToolCall:
    def __init__(self, id: str, name: str, input: dict):
        self.id = id
        self.name = name
        self.input = input


@pytest.mark.asyncio
async def test_dispatcher_records_duration_on_success():
    async def slow_handler(args: dict) -> str:
        await asyncio.sleep(0.05)
        return "ok"

    log = start_recording()
    calls = [FakeToolCall(id="t1", name="slow", input={"x": 1})]
    await dispatch_tools(calls, {"slow": slow_handler})

    assert len(log) == 1
    assert log[0].name == "slow"
    assert log[0].succeeded is True
    assert log[0].duration_ms is not None
    assert log[0].duration_ms >= 50.0
    assert log[0].duration_ms < 500.0


@pytest.mark.asyncio
async def test_dispatcher_records_duration_on_error():
    async def boom(args: dict) -> str:
        await asyncio.sleep(0.01)
        raise ValueError("boom")

    log = start_recording()
    calls = [FakeToolCall(id="t1", name="boom", input={})]
    await dispatch_tools(calls, {"boom": boom})

    assert len(log) == 1
    assert log[0].succeeded is False
    assert log[0].duration_ms is not None
    assert log[0].duration_ms >= 10.0


@pytest.mark.asyncio
async def test_dispatcher_records_zero_duration_for_unknown_tool():
    log = start_recording()
    calls = [FakeToolCall(id="t1", name="missing", input={})]
    await dispatch_tools(calls, {})

    assert len(log) == 1
    assert log[0].succeeded is False
    # Unknown tool: handler never ran, duration is 0.0 (not None) so the
    # entry is still discoverable in timing summaries.
    assert log[0].duration_ms == 0.0

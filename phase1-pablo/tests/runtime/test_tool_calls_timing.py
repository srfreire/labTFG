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

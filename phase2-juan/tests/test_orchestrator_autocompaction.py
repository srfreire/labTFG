"""Tests for the Orchestrator chat-history autocompaction (M12).

The orchestrator caps its own context window: once the chat history grows
past a message or character threshold, the oldest turns are replaced by a
deterministic audit summary that preserves the active pipeline state. The
mechanism uses no LLM call, so it is fully unit-testable without services.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from simlab.orchestrator import (
    AUTOCOMPACT_KEEP_MESSAGES,
    AUTOCOMPACT_MESSAGE_THRESHOLD,
    Orchestrator,
)


def _make_orchestrator() -> Orchestrator:
    return Orchestrator(client=MagicMock(), services=MagicMock())


def _make_history(n: int) -> list[dict]:
    """Alternating user/assistant string turns."""
    msgs: list[dict] = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"mensaje {i}"})
    return msgs


def test_no_autocompaction_below_thresholds():
    orch = _make_orchestrator()
    orch._messages = _make_history(5)
    before = list(orch._messages)

    assert orch._maybe_autocompact_history() is None
    assert orch._messages == before


def test_autocompaction_triggers_over_message_threshold():
    orch = _make_orchestrator()
    total = AUTOCOMPACT_MESSAGE_THRESHOLD + 1
    orch._messages = _make_history(total)

    payload = orch._maybe_autocompact_history()

    assert payload is not None
    keep = AUTOCOMPACT_KEEP_MESSAGES
    # History is now a single summary message followed by the kept tail.
    assert len(orch._messages) == keep + 1
    assert orch._messages[0]["role"] == "assistant"
    assert payload["retained_messages"] == keep
    assert payload["compacted_messages"] == total - keep
    # The newest turns survive verbatim.
    assert orch._messages[-1]["content"] == f"mensaje {total - 1}"


def test_summary_is_auditable_and_preserves_pipeline_state():
    orch = _make_orchestrator()
    orch._state = {"experiment_id": "exp-123", "seed": 42}
    orch._messages = _make_history(AUTOCOMPACT_MESSAGE_THRESHOLD + 1)

    orch._maybe_autocompact_history()
    summary = orch._messages[0]["content"]

    assert "<orchestrator_internal_note>" in summary
    assert "experiment_id=exp-123" in summary
    assert "seed=42" in summary


def test_compaction_summary_is_deterministic():
    orch = _make_orchestrator()
    orch._state = {"experiment_id": "exp-123", "seed": 42}
    messages = _make_history(20)

    first = orch._build_context_compaction_summary(
        messages, compacted_messages=20, retained_messages=10, char_count=999
    )
    second = orch._build_context_compaction_summary(
        messages, compacted_messages=20, retained_messages=10, char_count=999
    )

    assert first == second

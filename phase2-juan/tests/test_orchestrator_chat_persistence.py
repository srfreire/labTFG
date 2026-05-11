"""Tests for the Orchestrator chat-history persistence hook (P2-003)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from simlab.orchestrator import Orchestrator


def _make_response(blocks):
    return SimpleNamespace(content=blocks, stop_reason="end_turn")


def _make_text_response(text: str):
    return _make_response([SimpleNamespace(type="text", text=text)])


def _make_services_with_capturing_db():
    """Build a Services-like mock whose db.get_session yields a session
    whose execute() captures the rows passed in.
    """
    captured: dict[str, list[dict]] = {"rows": []}
    session = MagicMock()

    async def fake_execute(_stmt, rows):
        captured["rows"].extend(rows)

    session.execute = fake_execute
    session.commit = AsyncMock()

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)

    db = MagicMock()
    db.get_session = MagicMock(return_value=cm)

    services = MagicMock()
    services.db = db
    return services, captured


# ---------------------------------------------------------------------------
# AC1 — each Orchestrator gets its own session_id
# ---------------------------------------------------------------------------


def test_session_id_is_per_instance():
    o1 = Orchestrator(client=MagicMock(), services=MagicMock())
    o2 = Orchestrator(client=MagicMock(), services=MagicMock())
    assert isinstance(o1._session_id, uuid.UUID)
    assert isinstance(o2._session_id, uuid.UUID)
    assert o1._session_id != o2._session_id


# ---------------------------------------------------------------------------
# AC2 — flag OFF → zero rows written
# ---------------------------------------------------------------------------


async def test_flag_off_does_not_persist(monkeypatch):
    services, captured = _make_services_with_capturing_db()
    orch = Orchestrator(client=MagicMock(), services=services)

    fake_settings = MagicMock(
        ENABLE_CHAT_PERSISTENCE=False, ENABLE_KNOWLEDGE_READ=False
    )
    monkeypatch.setattr(
        "simlab.orchestrator.load_settings", lambda: fake_settings
    )

    with patch(
        "simlab.orchestrator.run_agent_loop",
        new=AsyncMock(return_value=_make_text_response("hi")),
    ):
        await orch.chat("hello")

    assert captured["rows"] == []
    services.db.get_session.assert_not_called()


# ---------------------------------------------------------------------------
# AC3 — flag ON, simple text turn → 2 rows (user + assistant) same session
# ---------------------------------------------------------------------------


async def test_flag_on_persists_user_and_assistant_rows(monkeypatch):
    services, captured = _make_services_with_capturing_db()
    orch = Orchestrator(client=MagicMock(), services=services)

    fake_settings = MagicMock(
        ENABLE_CHAT_PERSISTENCE=True, ENABLE_KNOWLEDGE_READ=False
    )
    monkeypatch.setattr(
        "simlab.orchestrator.load_settings", lambda: fake_settings
    )

    with patch(
        "simlab.orchestrator.run_agent_loop",
        new=AsyncMock(return_value=_make_text_response("here is my reply")),
    ):
        await orch.chat("can you do X?")

    assert len(captured["rows"]) == 2
    roles = [r["role"] for r in captured["rows"]]
    assert roles == ["user", "assistant"]
    assert captured["rows"][0]["content"] == "can you do X?"
    assert captured["rows"][1]["content"] == "here is my reply"
    assert all(r["session_id"] == orch._session_id for r in captured["rows"])


# ---------------------------------------------------------------------------
# AC4 — flag ON, tool_use in final response → tool_use rows with names
# ---------------------------------------------------------------------------


async def test_flag_on_persists_tool_use_blocks_from_response(monkeypatch):
    services, captured = _make_services_with_capturing_db()
    orch = Orchestrator(client=MagicMock(), services=services)

    fake_settings = MagicMock(
        ENABLE_CHAT_PERSISTENCE=True, ENABLE_KNOWLEDGE_READ=False
    )
    monkeypatch.setattr(
        "simlab.orchestrator.load_settings", lambda: fake_settings
    )

    response = _make_response(
        [
            SimpleNamespace(type="text", text="ok, running tools"),
            SimpleNamespace(
                type="tool_use",
                id="tu1",
                name="run_simulation",
                input={"steps": 50},
            ),
            SimpleNamespace(
                type="tool_use", id="tu2", name="analyze_results", input={}
            ),
        ]
    )

    with patch(
        "simlab.orchestrator.run_agent_loop",
        new=AsyncMock(return_value=response),
    ):
        await orch.chat("simulate")

    roles = [r["role"] for r in captured["rows"]]
    # 1 user + 1 assistant (text) + 2 tool_use = 4 rows
    assert roles == ["user", "assistant", "tool_use", "tool_use"]
    tool_use_rows = [r for r in captured["rows"] if r["role"] == "tool_use"]
    assert {r["tool_name"] for r in tool_use_rows} == {
        "run_simulation",
        "analyze_results",
    }


# ---------------------------------------------------------------------------
# AC5 — experiment_id snapshot at write time
# ---------------------------------------------------------------------------


async def test_experiment_id_is_snapshotted(monkeypatch):
    services, captured = _make_services_with_capturing_db()
    orch = Orchestrator(client=MagicMock(), services=services)

    fake_settings = MagicMock(
        ENABLE_CHAT_PERSISTENCE=True, ENABLE_KNOWLEDGE_READ=False
    )
    monkeypatch.setattr(
        "simlab.orchestrator.load_settings", lambda: fake_settings
    )

    # First turn — no experiment yet
    with patch(
        "simlab.orchestrator.run_agent_loop",
        new=AsyncMock(return_value=_make_text_response("a")),
    ):
        await orch.chat("hi")
    first_turn_eids = [r["experiment_id"] for r in captured["rows"]]
    assert all(eid is None for eid in first_turn_eids)

    # Set experiment_id, then second turn
    exp_id = uuid.uuid4()
    orch._state["experiment_id"] = exp_id
    captured["rows"].clear()

    with patch(
        "simlab.orchestrator.run_agent_loop",
        new=AsyncMock(return_value=_make_text_response("b")),
    ):
        await orch.chat("again")

    second_turn_eids = [r["experiment_id"] for r in captured["rows"]]
    assert all(eid == exp_id for eid in second_turn_eids)


# ---------------------------------------------------------------------------
# AC6 — persist failure does NOT raise into chat(); user gets reply
# ---------------------------------------------------------------------------


async def test_persist_failure_does_not_propagate(monkeypatch, caplog):
    services = MagicMock()
    db = MagicMock()
    db.get_session = MagicMock(side_effect=RuntimeError("DB blew up"))
    services.db = db

    orch = Orchestrator(client=MagicMock(), services=services)

    fake_settings = MagicMock(
        ENABLE_CHAT_PERSISTENCE=True, ENABLE_KNOWLEDGE_READ=False
    )
    monkeypatch.setattr(
        "simlab.orchestrator.load_settings", lambda: fake_settings
    )

    with patch(
        "simlab.orchestrator.run_agent_loop",
        new=AsyncMock(return_value=_make_text_response("survives the failure")),
    ):
        with caplog.at_level("WARNING"):
            text = await orch.chat("test")

    assert text == "survives the failure"
    assert any("chat persistence failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Sanity — string experiment_id is coerced to UUID
# ---------------------------------------------------------------------------


async def test_string_experiment_id_is_coerced_to_uuid(monkeypatch):
    services, captured = _make_services_with_capturing_db()
    orch = Orchestrator(client=MagicMock(), services=services)
    exp_id = uuid.uuid4()
    orch._state["experiment_id"] = str(exp_id)

    fake_settings = MagicMock(
        ENABLE_CHAT_PERSISTENCE=True, ENABLE_KNOWLEDGE_READ=False
    )
    monkeypatch.setattr(
        "simlab.orchestrator.load_settings", lambda: fake_settings
    )

    with patch(
        "simlab.orchestrator.run_agent_loop",
        new=AsyncMock(return_value=_make_text_response("ok")),
    ):
        await orch.chat("hi")

    assert captured["rows"][0]["experiment_id"] == exp_id


async def test_invalid_string_experiment_id_falls_back_to_none(monkeypatch):
    services, captured = _make_services_with_capturing_db()
    orch = Orchestrator(client=MagicMock(), services=services)
    orch._state["experiment_id"] = "not-a-uuid"

    fake_settings = MagicMock(
        ENABLE_CHAT_PERSISTENCE=True, ENABLE_KNOWLEDGE_READ=False
    )
    monkeypatch.setattr(
        "simlab.orchestrator.load_settings", lambda: fake_settings
    )

    with patch(
        "simlab.orchestrator.run_agent_loop",
        new=AsyncMock(return_value=_make_text_response("ok")),
    ):
        await orch.chat("hi")

    assert all(r["experiment_id"] is None for r in captured["rows"])


# Hidden import (used by AsyncMock side_effect helper)
_ = pytest  # silence unused-import warning if pytest isn't directly referenced

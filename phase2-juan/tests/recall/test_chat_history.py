"""Unit + integration tests for the chat_history serializer/writer (P2-002)."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from simlab.recall.chat_history import persist_messages, serialize_message

SID = uuid.uuid4()
EID = uuid.uuid4()


# ---------------------------------------------------------------------------
# AC1 — user string → one user row
# ---------------------------------------------------------------------------


def test_user_string_message_yields_one_user_row():
    msg = {"role": "user", "content": "hello, world"}
    rows = serialize_message(msg, session_id=SID, experiment_id=EID)

    assert len(rows) == 1
    r = rows[0]
    assert r["role"] == "user"
    assert r["content"] == "hello, world"
    assert r["session_id"] == SID
    assert r["experiment_id"] == EID
    assert r["tool_name"] is None
    assert isinstance(r["id"], uuid.UUID)


def test_empty_user_string_yields_no_rows():
    rows = serialize_message(
        {"role": "user", "content": "   "}, session_id=SID, experiment_id=None
    )
    assert rows == []


# ---------------------------------------------------------------------------
# AC2 — assistant with 1 text + 2 tool_use → 3 rows
# ---------------------------------------------------------------------------


def test_assistant_text_plus_two_tool_use_yields_three_rows():
    blocks = [
        SimpleNamespace(type="text", text="thinking…"),
        SimpleNamespace(type="tool_use", name="run_simulation", input={"steps": 10}),
        SimpleNamespace(type="tool_use", name="analyze_results", input={}),
    ]
    rows = serialize_message(
        {"role": "assistant", "content": blocks}, session_id=SID, experiment_id=EID
    )

    assert len(rows) == 3
    assert rows[0]["role"] == "assistant"
    assert rows[0]["content"] == "thinking…"
    assert rows[0]["tool_name"] is None

    assert rows[1]["role"] == "tool_use"
    assert rows[1]["tool_name"] == "run_simulation"
    assert json.loads(rows[1]["content"]) == {
        "name": "run_simulation",
        "input": {"steps": 10},
    }

    assert rows[2]["role"] == "tool_use"
    assert rows[2]["tool_name"] == "analyze_results"


# ---------------------------------------------------------------------------
# AC3 — user with tool_result blocks → N tool_result rows
# ---------------------------------------------------------------------------


def test_user_tool_result_blocks_yield_tool_result_rows():
    msg = {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "tu1", "content": "ok"},
            {"type": "tool_result", "tool_use_id": "tu2", "content": [1, 2, 3]},
        ],
    }
    names = {"tu1": "run_simulation", "tu2": "analyze_results"}
    rows = serialize_message(
        msg, session_id=SID, experiment_id=EID, tool_use_names=names
    )

    assert len(rows) == 2
    assert rows[0]["role"] == "tool_result"
    assert rows[0]["tool_name"] == "run_simulation"
    assert json.loads(rows[0]["content"]) == "ok"

    assert rows[1]["role"] == "tool_result"
    assert rows[1]["tool_name"] == "analyze_results"
    assert json.loads(rows[1]["content"]) == [1, 2, 3]


def test_user_tool_result_unknown_tool_use_id_yields_null_tool_name():
    msg = {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "missing", "content": "x"}
        ],
    }
    rows = serialize_message(
        msg, session_id=SID, experiment_id=None, tool_use_names={}
    )
    assert len(rows) == 1
    assert rows[0]["tool_name"] is None


# ---------------------------------------------------------------------------
# AC4 — empty/whitespace text blocks are skipped
# ---------------------------------------------------------------------------


def test_assistant_empty_text_blocks_are_skipped():
    blocks = [
        SimpleNamespace(type="text", text=""),
        SimpleNamespace(type="text", text="   "),
        SimpleNamespace(type="text", text="real content"),
        SimpleNamespace(type="tool_use", name="x", input={}),
    ]
    rows = serialize_message(
        {"role": "assistant", "content": blocks}, session_id=SID, experiment_id=None
    )
    # 1 assistant (the non-empty text) + 1 tool_use
    assert len(rows) == 2
    assert rows[0]["content"] == "real content"


def test_assistant_with_non_list_content_yields_no_rows():
    rows = serialize_message(
        {"role": "assistant", "content": None}, session_id=SID, experiment_id=None
    )
    assert rows == []


def test_unknown_role_yields_no_rows():
    rows = serialize_message(
        {"role": "system", "content": "stuff"}, session_id=SID, experiment_id=None
    )
    assert rows == []


def test_context_summary_role_serializes_as_audit_row():
    rows = serialize_message(
        {"role": "context_summary", "content": "Contexto compactado: 12 mensajes"},
        session_id=SID,
        experiment_id=EID,
    )

    assert len(rows) == 1
    assert rows[0]["role"] == "context_summary"
    assert rows[0]["content"] == "Contexto compactado: 12 mensajes"
    assert rows[0]["tool_name"] is None


# ---------------------------------------------------------------------------
# AC5 — persist_messages bulk-inserts in one round-trip
# ---------------------------------------------------------------------------


async def test_persist_messages_uses_one_execute_call():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    rows = [
        {
            "id": uuid.uuid4(),
            "session_id": SID,
            "experiment_id": None,
            "role": "user",
            "content": f"msg {i}",
            "tool_name": None,
        }
        for i in range(10)
    ]

    await persist_messages(session, rows)

    assert session.execute.call_count == 1
    args, _ = session.execute.call_args
    # Second positional arg is the rows list — confirms bulk path
    assert args[1] == rows
    session.commit.assert_awaited_once()


async def test_persist_messages_empty_rows_noop():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    await persist_messages(session, [])

    session.execute.assert_not_called()
    session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# AC6 — DB error inside persist_messages does NOT propagate
# ---------------------------------------------------------------------------


async def test_persist_messages_swallows_db_errors(caplog):
    session = MagicMock()
    session.execute = AsyncMock(side_effect=RuntimeError("DB down"))
    session.commit = AsyncMock()

    rows = [
        {
            "id": uuid.uuid4(),
            "session_id": SID,
            "experiment_id": None,
            "role": "user",
            "content": "x",
            "tool_name": None,
        }
    ]

    # Must not raise
    with caplog.at_level("WARNING"):
        await persist_messages(session, rows)

    assert any(
        "persist_messages: bulk insert failed" in r.message for r in caplog.records
    )


# ---------------------------------------------------------------------------
# Integration — real Postgres round-trip (gated by marker)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_persist_messages_integration_roundtrip():
    """End-to-end: persist 10 rows and verify they show up in the table.

    Uses a temp schema (``Base.metadata.create_all``) so the test works
    regardless of which migrations have been applied to the live DB.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from shared.models import Base, ChatMessage
    from shared.settings import load_settings

    engine = create_async_engine(load_settings().POSTGRES_DSN)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sess_factory = async_sessionmaker(engine, expire_on_commit=False)

    session_id = uuid.uuid4()
    rows = [
        {
            "id": uuid.uuid4(),
            "session_id": session_id,
            "experiment_id": None,
            "role": "user",
            "content": f"msg {i}",
            "tool_name": None,
        }
        for i in range(10)
    ]

    async with sess_factory() as session:
        await persist_messages(session, rows)

    async with sess_factory() as session:
        result = await session.execute(
            select(ChatMessage).where(ChatMessage.session_id == session_id)
        )
        stored = result.scalars().all()
        assert len(stored) == 10

    await engine.dispose()

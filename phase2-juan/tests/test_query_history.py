"""Tests for ``query_history`` and ``_format_rows`` (sim-recall P3-002)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import simlab.nlsql as nlsql
from simlab.nlsql import _MAX_LIMIT, _format_rows, query_history

# ---------------------------------------------------------------------------
# _format_rows — markdown rendering
# ---------------------------------------------------------------------------


def test_format_rows_empty_returns_sin_resultados():
    assert _format_rows([]) == "> Sin resultados."


def test_format_rows_header_from_first_row_keys():
    rows = [
        {"id": "1", "content": "hello"},
        {"id": "2", "content": "world"},
    ]
    out = _format_rows(rows)
    assert "| id | content |" in out
    assert "| 1 | hello |" in out
    assert "| 2 | world |" in out
    # Separator row
    assert "| --- | --- |" in out
    # No truncation note when below limit
    assert "filas" not in out.lower() or "primeras" not in out


def test_format_rows_at_max_limit_appends_truncation_note():
    rows = [{"id": str(i)} for i in range(_MAX_LIMIT)]
    out = _format_rows(rows)
    assert out.endswith(f"_Mostrando primeras {_MAX_LIMIT} filas._")


# ---------------------------------------------------------------------------
# AC1 — happy path with 3 rows returns markdown table
# ---------------------------------------------------------------------------


async def test_query_history_happy_path():
    rows = [
        {"id": "a", "role": "user", "content": "hi"},
        {"id": "b", "role": "assistant", "content": "hello"},
        {"id": "c", "role": "user", "content": "bye"},
    ]
    with patch.object(
        nlsql, "_plan", new=AsyncMock(return_value={"sql": "SELECT * FROM chat_messages"})
    ), patch.object(nlsql, "_execute", new=AsyncMock(return_value=rows)):
        out = await query_history("¿qué dije?", db=MagicMock())

    assert "| id | role | content |" in out
    assert "| a | user | hi |" in out
    assert "| c | user | bye |" in out


# ---------------------------------------------------------------------------
# AC2 — out_of_scope plan returns the markdown sentence; _execute not called
# ---------------------------------------------------------------------------


async def test_query_history_out_of_scope_skips_execute():
    plan = AsyncMock(return_value={"error": "out_of_scope", "reason": "no SQL"})
    execute = AsyncMock(return_value=[])
    with patch.object(nlsql, "_plan", new=plan), patch.object(
        nlsql, "_execute", new=execute
    ):
        out = await query_history("¿qué hora es?", db=MagicMock())

    assert "alcance" in out  # the out-of-scope sentence
    execute.assert_not_called()


async def test_query_history_empty_sql_treated_as_out_of_scope():
    """When the planner returns no SQL string, treat as out-of-scope."""
    with patch.object(
        nlsql, "_plan", new=AsyncMock(return_value={"sql": ""})
    ), patch.object(nlsql, "_execute", new=AsyncMock()) as execute:
        out = await query_history("?", db=MagicMock())

    assert "alcance" in out
    execute.assert_not_called()


# ---------------------------------------------------------------------------
# AC3 — _execute raising does not propagate
# ---------------------------------------------------------------------------


async def test_query_history_execute_raises_returns_graceful_markdown():
    with patch.object(
        nlsql,
        "_plan",
        new=AsyncMock(return_value={"sql": "SELECT * FROM chat_messages"}),
    ), patch.object(
        nlsql, "_execute", new=AsyncMock(side_effect=RuntimeError("DB down"))
    ):
        out = await query_history("anything", db=MagicMock())

    assert "Error al ejecutar" in out


async def test_query_history_execute_returns_none_yields_error_markdown():
    """_execute returning None (its internal error path) → graceful message."""
    with patch.object(
        nlsql,
        "_plan",
        new=AsyncMock(return_value={"sql": "SELECT * FROM chat_messages"}),
    ), patch.object(nlsql, "_execute", new=AsyncMock(return_value=None)):
        out = await query_history("anything", db=MagicMock())

    assert "Error al ejecutar" in out


# ---------------------------------------------------------------------------
# AC4 — empty rows → "> Sin resultados."
# ---------------------------------------------------------------------------


async def test_query_history_empty_rows_returns_sin_resultados():
    with patch.object(
        nlsql,
        "_plan",
        new=AsyncMock(return_value={"sql": "SELECT * FROM chat_messages"}),
    ), patch.object(nlsql, "_execute", new=AsyncMock(return_value=[])):
        out = await query_history("anything", db=MagicMock())

    assert out == "> Sin resultados."


# ---------------------------------------------------------------------------
# AC5 — at _MAX_LIMIT rows → truncation note
# ---------------------------------------------------------------------------


async def test_query_history_at_max_limit_appends_truncation_note():
    rows = [{"id": str(i)} for i in range(_MAX_LIMIT)]
    with patch.object(
        nlsql,
        "_plan",
        new=AsyncMock(return_value={"sql": "SELECT id FROM chat_messages"}),
    ), patch.object(nlsql, "_execute", new=AsyncMock(return_value=rows)):
        out = await query_history("anything", db=MagicMock())

    assert out.endswith(f"_Mostrando primeras {_MAX_LIMIT} filas._")


# ---------------------------------------------------------------------------
# Validator-rejected SQL → graceful markdown
# ---------------------------------------------------------------------------


async def test_query_history_validator_rejection_returns_markdown():
    """When the planner produces a disallowed query, the validator's
    reason surfaces inside the markdown — no stack trace."""
    with patch.object(
        nlsql,
        "_plan",
        new=AsyncMock(return_value={"sql": "DELETE FROM chat_messages"}),
    ), patch.object(nlsql, "_execute", new=AsyncMock()) as execute:
        out = await query_history("borra todo", db=MagicMock())

    assert out.startswith("> Consulta rechazada")
    execute.assert_not_called()


# ---------------------------------------------------------------------------
# AC6 — ENABLE_QUERY_HISTORY flag
# ---------------------------------------------------------------------------


def test_enable_query_history_default_false():
    from shared.settings import Settings

    assert Settings().ENABLE_QUERY_HISTORY is False


def test_enable_query_history_env_override(monkeypatch):
    from shared.settings import load_settings

    monkeypatch.setenv("ENABLE_QUERY_HISTORY", "true")
    assert load_settings().ENABLE_QUERY_HISTORY is True

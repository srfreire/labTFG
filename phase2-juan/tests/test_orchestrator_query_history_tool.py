"""Tests for the Orchestrator query_history tool wiring (sim-recall P3-003)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from simlab.orchestrator import (
    _QUERY_HISTORY_PROMPT_SECTION,
    QUERY_HISTORY_TOOL,
    Orchestrator,
)

from shared.settings import Settings


def _make_orch() -> Orchestrator:
    return Orchestrator(client=MagicMock(), services=MagicMock())


# ---------------------------------------------------------------------------
# AC1 — flag OFF → no tool, no registry entry
# ---------------------------------------------------------------------------


def test_flag_off_omits_query_history_tool():
    orch = _make_orch()
    tools, registry = orch._build_tools(Settings(ENABLE_QUERY_HISTORY=False))

    names = {t["name"] for t in tools}
    assert "query_history" not in names
    assert "query_history" not in registry


# ---------------------------------------------------------------------------
# AC2 — flag ON → tool registered + routes to query_history
# ---------------------------------------------------------------------------


def test_flag_on_registers_query_history_tool():
    orch = _make_orch()
    tools, registry = orch._build_tools(Settings(ENABLE_QUERY_HISTORY=True))

    names = {t["name"] for t in tools}
    assert "query_history" in names
    assert "query_history" in registry
    # Tool schema is the canonical one
    qh_schema = next(t for t in tools if t["name"] == "query_history")
    assert qh_schema is QUERY_HISTORY_TOOL


async def test_flag_on_handler_routes_to_query_history():
    orch = _make_orch()
    orch._services.db = MagicMock()
    # Patch BEFORE _build_tools so the inner `from simlab.nlsql import ...`
    # picks up the mock at registration time.
    with patch(
        "simlab.nlsql.query_history",
        new=AsyncMock(return_value="| col |\n| --- |\n| value |"),
    ) as fn:
        _, registry = orch._build_tools(Settings(ENABLE_QUERY_HISTORY=True))
        handler = registry["query_history"]
        out = await handler({"question": "¿qué experimentos?"})

    fn.assert_awaited_once()
    assert "| value |" in out


async def test_handler_returns_friendly_message_on_empty_question():
    orch = _make_orch()
    orch._services.db = MagicMock()
    _, registry = orch._build_tools(Settings(ENABLE_QUERY_HISTORY=True))
    handler = registry["query_history"]

    out = await handler({"question": ""})
    assert "vacía" in out.lower() or "vacia" in out.lower()


async def test_handler_returns_friendly_message_when_db_none():
    orch = _make_orch()
    orch._services.db = None
    _, registry = orch._build_tools(Settings(ENABLE_QUERY_HISTORY=True))
    handler = registry["query_history"]

    out = await handler({"question": "anything"})
    assert "no disponible" in out.lower()


# ---------------------------------------------------------------------------
# AC3 — flag toggles the system prompt section
# ---------------------------------------------------------------------------


def test_system_prompt_includes_section_when_flag_on():
    orch = _make_orch()
    on = orch._build_system_prompt(Settings(ENABLE_QUERY_HISTORY=True))
    off = orch._build_system_prompt(Settings(ENABLE_QUERY_HISTORY=False))

    assert _QUERY_HISTORY_PROMPT_SECTION in on
    assert _QUERY_HISTORY_PROMPT_SECTION not in off


def test_query_history_section_is_orthogonal_to_knowledge_read():
    """Both flags can be on simultaneously and both sections appear."""
    orch = _make_orch()
    prompt = orch._build_system_prompt(
        Settings(ENABLE_QUERY_HISTORY=True, ENABLE_KNOWLEDGE_READ=True)
    )
    assert _QUERY_HISTORY_PROMPT_SECTION in prompt
    assert "Knowledge Backbone" in prompt

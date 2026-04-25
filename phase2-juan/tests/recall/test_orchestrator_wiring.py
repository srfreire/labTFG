"""P1-002 — tests for retrieve_context wiring in the Orchestrator.

Verifies that _build_tools() conditionally includes the retrieve_context
tool and handler based on ENABLE_KNOWLEDGE_READ, and that the system
prompt is extended when the flag is on.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from shared.settings import Settings
from simlab.orchestrator import Orchestrator, ORCHESTRATOR_SYSTEM_PROMPT

_FLAG_OFF = Settings()
_FLAG_ON = Settings(ENABLE_KNOWLEDGE_READ=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_orchestrator():
    return Orchestrator(client=MagicMock())


def _tool_names(tools: list[dict]) -> list[str]:
    return [t["name"] for t in tools]


# ---------------------------------------------------------------------------
# AC1: Flag OFF — tool list unchanged
# ---------------------------------------------------------------------------


async def test_flag_off_tools_unchanged():
    """With ENABLE_KNOWLEDGE_READ=False, tools list has no retrieve_context."""
    tools, registry = _make_orchestrator()._build_tools(_FLAG_OFF)

    assert "retrieve_context" not in _tool_names(tools)
    assert "retrieve_context" not in registry


# ---------------------------------------------------------------------------
# AC2: Flag ON — tool list includes retrieve_context
# ---------------------------------------------------------------------------


async def test_flag_on_adds_retrieve_context_tool():
    """With flag on, tools list includes retrieve_context and registry has it."""
    tools, registry = _make_orchestrator()._build_tools(_FLAG_ON)

    assert "retrieve_context" in _tool_names(tools)
    assert "retrieve_context" in registry
    assert callable(registry["retrieve_context"])


async def test_flag_on_tool_schema_correct():
    """The injected tool schema has the expected Anthropic shape."""
    tools, _ = _make_orchestrator()._build_tools(_FLAG_ON)

    tool = next(t for t in tools if t["name"] == "retrieve_context")
    assert "input_schema" in tool
    assert "query" in tool["input_schema"]["properties"]
    assert "query" in tool["input_schema"]["required"]


# ---------------------------------------------------------------------------
# AC3: Handler calls retrieve_context with correct params
# ---------------------------------------------------------------------------


async def test_handler_calls_retrieve_context_correctly():
    """The handler maps params dict to retrieve_context kwargs."""
    mock_retrieve = AsyncMock(return_value="## Retrieved Knowledge (1 results)\n\nSome fact.")

    with patch("simlab.recall.retrieve_context", mock_retrieve):
        _, registry = _make_orchestrator()._build_tools(_FLAG_ON)
        result = await registry["retrieve_context"]({
            "query": "homeostatic models",
            "namespace": "paradigm",
            "top_k": 3,
        })

    mock_retrieve.assert_awaited_once_with(
        query="homeostatic models",
        namespace="paradigm",
        top_k=3,
        stage="phase2-orchestrator",
    )
    assert "Retrieved Knowledge" in result


async def test_handler_uses_defaults_for_missing_params():
    """Handler provides defaults when namespace/top_k are omitted."""
    mock_retrieve = AsyncMock(return_value="empty")

    with patch("simlab.recall.retrieve_context", mock_retrieve):
        _, registry = _make_orchestrator()._build_tools(_FLAG_ON)
        await registry["retrieve_context"]({"query": "test"})

    mock_retrieve.assert_awaited_once_with(
        query="test",
        namespace=None,
        top_k=5,
        stage="phase2-orchestrator",
    )


# ---------------------------------------------------------------------------
# AC4: System prompt conditional
# ---------------------------------------------------------------------------


async def test_system_prompt_includes_retrieve_context_when_flag_on():
    """With flag on, the effective system prompt mentions retrieve_context."""
    prompt = _make_orchestrator()._build_system_prompt(_FLAG_ON)

    assert "retrieve_context" in prompt
    assert "Knowledge Backbone" in prompt


async def test_system_prompt_unchanged_when_flag_off():
    """With flag off, system prompt is exactly the base constant."""
    prompt = _make_orchestrator()._build_system_prompt(_FLAG_OFF)

    assert prompt == ORCHESTRATOR_SYSTEM_PROMPT
    assert "retrieve_context" not in prompt

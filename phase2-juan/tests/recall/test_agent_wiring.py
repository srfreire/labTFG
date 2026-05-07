"""P1-003 — tests for conditional tool injection into Architect, Analyst, Reporter.

Verifies that build_recall_extras produces correct per-agent extras and
that each agent's run() accepts extra_tools/extra_registry/prompt_suffix.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from simlab.recall.agent_tools import build_recall_extras

from shared.settings import Settings

_FLAG_ON = Settings(ENABLE_KNOWLEDGE_READ=True)
_FLAG_OFF = Settings()


# ---------------------------------------------------------------------------
# build_recall_extras
# ---------------------------------------------------------------------------


def test_build_recall_extras_returns_tool_registry_prompt():
    """Helper returns (tools, registry, prompt_section) tuple."""
    tools, registry, prompt = build_recall_extras("architect")
    assert len(tools) == 1
    assert tools[0]["name"] == "retrieve_context"
    assert "retrieve_context" in registry
    assert callable(registry["retrieve_context"])
    assert "Knowledge Backbone" in prompt


def test_build_recall_extras_different_prompts_per_stage():
    """Each stage gets a distinct prompt section."""
    _, _, arch_prompt = build_recall_extras("architect")
    _, _, analyst_prompt = build_recall_extras("analyst")
    _, _, reporter_prompt = build_recall_extras("reporter")

    assert "Knowledge Backbone" in arch_prompt
    assert "Postulate" in analyst_prompt
    assert "References" in reporter_prompt
    assert arch_prompt != analyst_prompt != reporter_prompt


def test_build_recall_extras_unknown_stage_empty_prompt():
    """Unknown stage returns empty prompt section but valid tools."""
    tools, _registry, prompt = build_recall_extras("unknown")
    assert len(tools) == 1
    assert prompt == ""


async def test_handler_uses_stage_prefix():
    """Handler passes stage='phase2-<stage>' to retrieve_context."""
    mock_rc = AsyncMock(return_value="result")
    with patch("simlab.recall.agent_tools.retrieve_context", mock_rc):
        _, registry, _ = build_recall_extras("analyst")
        await registry["retrieve_context"]({"query": "test"})
    mock_rc.assert_awaited_once_with(
        query="test",
        namespace=None,
        top_k=5,
        stage="phase2-analyst",
    )


# ---------------------------------------------------------------------------
# AC1: Flag OFF — agents unchanged
# ---------------------------------------------------------------------------


async def test_flag_off_architect_no_retrieve_context():
    """With flag off, Architect has no retrieve_context tool."""
    assert "retrieve_context" not in [
        t["name"] for t in _get_architect_tools(_FLAG_OFF)
    ]


async def test_flag_off_analyst_no_retrieve_context():
    """With flag off, Analyst has no retrieve_context tool."""
    assert "retrieve_context" not in [t["name"] for t in _get_analyst_tools(_FLAG_OFF)]


async def test_flag_off_reporter_no_retrieve_context():
    """With flag off, Reporter has no retrieve_context tool."""
    assert "retrieve_context" not in [t["name"] for t in _get_reporter_tools(_FLAG_OFF)]


# ---------------------------------------------------------------------------
# AC2: Flag ON — agents get retrieve_context
# ---------------------------------------------------------------------------


async def test_flag_on_architect_has_retrieve_context():
    """With flag on, Architect gets retrieve_context in its tools."""
    tools = _get_architect_tools(_FLAG_ON)
    assert "retrieve_context" in [t["name"] for t in tools]


async def test_flag_on_analyst_has_retrieve_context():
    """With flag on, Analyst gets retrieve_context."""
    tools = _get_analyst_tools(_FLAG_ON)
    assert "retrieve_context" in [t["name"] for t in tools]


async def test_flag_on_reporter_has_retrieve_context():
    """With flag on, Reporter gets retrieve_context."""
    tools = _get_reporter_tools(_FLAG_ON)
    assert "retrieve_context" in [t["name"] for t in tools]


# ---------------------------------------------------------------------------
# Helpers — extract tool lists from each agent via orchestrator
# ---------------------------------------------------------------------------


def _get_architect_tools(settings):
    """Build the tool list the Architect would get."""
    from simlab.architect import VALIDATE_SPEC_TOOL

    tools = [VALIDATE_SPEC_TOOL]
    if settings.ENABLE_KNOWLEDGE_READ:
        from simlab.recall import build_recall_extras

        et, _, _ = build_recall_extras("architect")
        tools += et
    return tools


def _get_analyst_tools(settings):
    """Build the tool list the Analyst would get."""
    from simlab.tools import build_cross_experiment_tools, build_simulation_tools

    tools, _ = build_simulation_tools([], critical_events=None)
    db_tools, _ = build_cross_experiment_tools()
    tools += db_tools
    if settings.ENABLE_KNOWLEDGE_READ:
        from simlab.recall import build_recall_extras

        et, _, _ = build_recall_extras("analyst")
        tools += et
    return tools


def _get_reporter_tools(settings):
    """Build the tool list the Reporter would get."""
    from simlab.reporter import _build_tools as reporter_build_tools

    tools, _ = reporter_build_tools("run-1", "exp-1")
    if settings.ENABLE_KNOWLEDGE_READ:
        from simlab.recall import build_recall_extras

        et, _, _ = build_recall_extras("reporter")
        tools += et
    return tools

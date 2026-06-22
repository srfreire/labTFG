"""P1-003 — tests for conditional tool injection into Architect, Analyst, Reporter.

Verifies that build_recall_extras produces correct per-agent extras and
that each agent's run() accepts extra_tools/extra_registry/prompt_suffix.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from simlab.orchestrator import Orchestrator
from simlab.recall.agent_tools import build_recall_extras

from shared.services import Services
from shared.settings import Settings

_FLAG_ON = Settings(ENABLE_KNOWLEDGE_READ=True)
_FLAG_OFF = Settings()


def _stub_services() -> Services:
    return Services(db=MagicMock(), storage=MagicMock())


def _stub_orchestrator_services() -> Services:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)

    db = MagicMock()
    db.get_session = MagicMock(return_value=cm)
    return Services(db=db, storage=MagicMock())


# ---------------------------------------------------------------------------
# build_recall_extras
# ---------------------------------------------------------------------------


def test_build_recall_extras_returns_tool_registry_prompt():
    """Helper returns (tools, registry, prompt_section) tuple."""
    tools, registry, prompt = build_recall_extras("architect", _stub_services())
    assert len(tools) == 1
    assert tools[0]["name"] == "retrieve_context"
    assert "retrieve_context" in registry
    assert callable(registry["retrieve_context"])
    assert "Knowledge Backbone" in prompt


def test_build_recall_extras_different_prompts_per_stage():
    """Each stage gets a distinct prompt section.

    Substrings are stage-unique: ``Knowledge Backbone`` only appears in
    the architect's section, ``Postulate`` in the analyst's, and
    ``References`` in the reporter's.
    """
    _, _, arch_prompt = build_recall_extras("architect", _stub_services())
    _, _, analyst_prompt = build_recall_extras("analyst", _stub_services())
    _, _, reporter_prompt = build_recall_extras("reporter", _stub_services())

    assert "Knowledge Backbone" in arch_prompt
    assert "Postulate" in analyst_prompt
    assert "References" in reporter_prompt
    assert arch_prompt != analyst_prompt != reporter_prompt


def test_build_recall_extras_unknown_stage_empty_prompt():
    """Unknown stage returns empty prompt section but valid tools."""
    tools, _registry, prompt = build_recall_extras("unknown", _stub_services())
    assert len(tools) == 1
    assert prompt == ""


async def test_handler_uses_stage_prefix():
    """Handler passes stage='phase2-<stage>' to retrieve_context."""
    mock_rc = AsyncMock(return_value="result")
    services = _stub_services()
    with patch("simlab.recall.agent_tools.retrieve_context", mock_rc):
        _, registry, _ = build_recall_extras("analyst", services)
        await registry["retrieve_context"]({"query": "test"})
    mock_rc.assert_awaited_once_with(
        services=services,
        query="test",
        namespace=None,
        top_k=3,
        stage="phase2-analyst",
    )


# ---------------------------------------------------------------------------
# Orchestrator wiring
# ---------------------------------------------------------------------------


def test_orchestrator_flag_off_does_not_initialise_recall_extras():
    orch = Orchestrator(client=MagicMock(), services=_stub_orchestrator_services())

    with patch("simlab.recall.build_recall_extras") as build:
        tools, registry = orch._build_tools(_FLAG_OFF)

    build.assert_not_called()
    assert "retrieve_context" not in [t["name"] for t in tools]
    assert "retrieve_context" not in registry


def test_orchestrator_flag_on_initialises_recall_extras_for_agent_stages():
    orch = Orchestrator(client=MagicMock(), services=_stub_orchestrator_services())

    with patch(
        "simlab.recall.build_recall_extras",
        return_value=([{"name": "retrieve_context"}], {"retrieve_context": AsyncMock()}, "prompt"),
    ) as build:
        tools, registry = orch._build_tools(_FLAG_ON)

    assert [call.args[0] for call in build.call_args_list] == [
        "architect",
        "analyst",
        "reporter",
    ]
    assert all(call.args[1] is orch._services for call in build.call_args_list)
    assert "retrieve_context" in [t["name"] for t in tools]
    assert "retrieve_context" in registry


async def test_create_environment_passes_recall_extras_to_architect():
    services = _stub_orchestrator_services()
    orch = Orchestrator(client=MagicMock(), services=services)
    extra_tools = [{"name": "retrieve_context"}]
    extra_registry = {"retrieve_context": AsyncMock(return_value="ctx")}

    with (
        patch(
            "simlab.recall.build_recall_extras",
            return_value=(extra_tools, extra_registry, "architect prompt"),
        ),
        patch("simlab.orchestrator.prefetch_knowledge", new=AsyncMock(return_value="kg")),
        patch("simlab.orchestrator.Architect") as architect_cls,
    ):
        architect = MagicMock()
        architect.run = AsyncMock(return_value='{"grid_width": 4, "grid_height": 4}')
        architect_cls.return_value = architect
        _tools, registry = orch._build_tools(_FLAG_ON)

        await registry["create_environment"]({"description": "homeostatic task"})

    architect.run.assert_awaited_once()
    kwargs = architect.run.await_args.kwargs
    assert kwargs["knowledge_context"] == "kg"
    assert kwargs["extra_tools"] is extra_tools
    assert kwargs["extra_registry"] is extra_registry
    assert kwargs["prompt_suffix"] == "architect prompt"

"""Tests for P4-001: retrieve_knowledge tool wiring into pipeline agents."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from decisionlab.adapters.mock import MockWebSearch
from decisionlab.agents.builder import Builder
from decisionlab.agents.builder_sub import BuilderSubAgent
from decisionlab.agents.deep_researcher import DeepResearcher
from decisionlab.agents.formalizer import Formalizer
from decisionlab.agents.formalizer_sub import FormalizerSubAgent
from decisionlab.agents.reasoner import Reasoner
from decisionlab.agents.reasoner_sub import ReasonerSubAgent
from decisionlab.agents.researcher import Researcher
from decisionlab.knowledge.retrieval.tool import RETRIEVE_KNOWLEDGE_SCHEMA

_MOCK_HANDLER = AsyncMock(return_value="## Retrieved Knowledge (0 results)")
_CLIENT = AsyncMock()
_SEARCH = MockWebSearch()


# ── AC1: Each agent includes retrieve_knowledge when infra is available ──


class TestToolPresent:
    """AC1: Each agent's tool list includes retrieve_knowledge when knowledge
    infrastructure is available (schema + handler provided)."""

    def test_researcher_has_retrieve_knowledge(self):
        r = Researcher(
            client=_CLIENT,
            search=_SEARCH,
            knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
            knowledge_tool_handler=_MOCK_HANDLER,
        )
        names = [t["name"] for t in r.tools]
        assert "retrieve_knowledge" in names
        assert "retrieve_knowledge" in r.registry

    def test_deep_researcher_has_retrieve_knowledge(self):
        dr = DeepResearcher(
            client=_CLIENT,
            search=_SEARCH,
            knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
            knowledge_tool_handler=_MOCK_HANDLER,
        )
        names = [t["name"] for t in dr.tools]
        assert "retrieve_knowledge" in names
        assert "retrieve_knowledge" in dr.registry

    def test_formalizer_sub_has_retrieve_knowledge(self):
        fs = FormalizerSubAgent(
            client=_CLIENT,
            research_prefix="research/run-1",
            knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
            knowledge_tool_handler=_MOCK_HANDLER,
        )
        names = [t["name"] for t in fs.tools]
        assert "retrieve_knowledge" in names
        assert "retrieve_knowledge" in fs.registry

    def test_reasoner_sub_has_retrieve_knowledge(self):
        rs = ReasonerSubAgent(
            client=_CLIENT,
            research_prefix="research/run-1",
            models_prefix="models/run-1",
            knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
            knowledge_tool_handler=_MOCK_HANDLER,
        )
        names = [t["name"] for t in rs.tools]
        assert "retrieve_knowledge" in names
        assert "retrieve_knowledge" in rs.registry

    def test_builder_sub_has_retrieve_knowledge(self):
        bs = BuilderSubAgent(
            client=_CLIENT,
            models_prefix="models/run-1",
            project_root=Path("/tmp"),
            knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
            knowledge_tool_handler=_MOCK_HANDLER,
        )
        names = [t["name"] for t in bs.tools]
        assert "retrieve_knowledge" in names
        assert "retrieve_knowledge" in bs.registry


# ── AC2: Tool NOT present when infra is unavailable ──


class TestToolAbsent:
    """AC2: Each agent's tool list does NOT include retrieve_knowledge when
    infrastructure is unavailable (no schema/handler provided)."""

    def test_researcher_no_retrieve_knowledge_by_default(self):
        r = Researcher(client=_CLIENT, search=_SEARCH)
        names = [t["name"] for t in r.tools]
        assert "retrieve_knowledge" not in names
        assert "retrieve_knowledge" not in r.registry

    def test_deep_researcher_no_retrieve_knowledge_by_default(self):
        dr = DeepResearcher(client=_CLIENT, search=_SEARCH)
        names = [t["name"] for t in dr.tools]
        assert "retrieve_knowledge" not in names
        assert "retrieve_knowledge" not in dr.registry

    def test_formalizer_sub_no_retrieve_knowledge_by_default(self):
        fs = FormalizerSubAgent(
            client=_CLIENT,
            research_prefix="research/run-1",
        )
        names = [t["name"] for t in fs.tools]
        assert "retrieve_knowledge" not in names
        assert "retrieve_knowledge" not in fs.registry

    def test_reasoner_sub_no_retrieve_knowledge_by_default(self):
        rs = ReasonerSubAgent(
            client=_CLIENT,
            research_prefix="research/run-1",
            models_prefix="models/run-1",
        )
        names = [t["name"] for t in rs.tools]
        assert "retrieve_knowledge" not in names
        assert "retrieve_knowledge" not in rs.registry

    def test_builder_sub_no_retrieve_knowledge_by_default(self):
        bs = BuilderSubAgent(
            client=_CLIENT,
            models_prefix="models/run-1",
            project_root=Path("/tmp"),
        )
        names = [t["name"] for t in bs.tools]
        assert "retrieve_knowledge" not in names
        assert "retrieve_knowledge" not in bs.registry

    def test_no_tool_when_only_schema_provided(self):
        """Both schema AND handler must be provided; schema alone is not enough."""
        r = Researcher(
            client=_CLIENT,
            search=_SEARCH,
            knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
            knowledge_tool_handler=None,
        )
        names = [t["name"] for t in r.tools]
        assert "retrieve_knowledge" not in names

    def test_no_tool_when_only_handler_provided(self):
        """Both schema AND handler must be provided; handler alone is not enough."""
        r = Researcher(
            client=_CLIENT,
            search=_SEARCH,
            knowledge_tool_schema=None,
            knowledge_tool_handler=_MOCK_HANDLER,
        )
        names = [t["name"] for t in r.tools]
        assert "retrieve_knowledge" not in names


# ── AC5: Dispatch works through existing dispatcher ──


@pytest.mark.asyncio
async def test_dispatch_retrieve_knowledge_through_registry():
    """AC5: retrieve_knowledge calls are dispatched via the agent's registry
    like any other tool (compatible with runtime/dispatcher.py)."""
    from decisionlab.runtime.dispatcher import dispatch_tools

    handler = AsyncMock(
        return_value="## Retrieved Knowledge (1 results)\n\n### Result 1"
    )

    bs = BuilderSubAgent(
        client=_CLIENT,
        models_prefix="models/run-1",
        project_root=Path("/tmp"),
        knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
        knowledge_tool_handler=handler,
    )

    # Simulate a tool_use call object
    call = AsyncMock()
    call.name = "retrieve_knowledge"
    call.id = "call-1"
    call.input = {"query": "Q-learning convergence patterns"}

    results = await dispatch_tools([call], bs.registry)
    assert len(results) == 1
    assert results[0]["content"].startswith("## Retrieved Knowledge")
    assert not results[0].get("is_error", False)
    handler.assert_called_once_with({"query": "Q-learning convergence patterns"})


# ── System prompt augmentation ──


class TestSystemPromptAugmentation:
    """Verify system prompts are augmented when knowledge tool is present."""

    def test_researcher_prompt_augmented(self):
        r = Researcher(
            client=_CLIENT,
            search=_SEARCH,
            knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
            knowledge_tool_handler=_MOCK_HANDLER,
        )
        assert r._has_knowledge is True

    def test_researcher_prompt_not_augmented_without_knowledge(self):
        r = Researcher(client=_CLIENT, search=_SEARCH)
        assert r._has_knowledge is False

    def test_formalizer_sub_prompt_augmented(self):
        fs = FormalizerSubAgent(
            client=_CLIENT,
            research_prefix="research/run-1",
            knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
            knowledge_tool_handler=_MOCK_HANDLER,
        )
        assert fs._has_knowledge is True

    def test_builder_sub_prompt_augmented(self):
        bs = BuilderSubAgent(
            client=_CLIENT,
            models_prefix="models/run-1",
            project_root=Path("/tmp"),
            knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
            knowledge_tool_handler=_MOCK_HANDLER,
        )
        assert bs._has_knowledge is True


# ── Orchestrators forward knowledge deps to sub-agents ──


class TestOrchestratorForwarding:
    """Verify orchestrators store knowledge deps for sub-agent creation."""

    def test_formalizer_stores_knowledge_deps(self):
        f = Formalizer(
            client=_CLIENT,
            research_prefix="research/run-1",
            knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
            knowledge_tool_handler=_MOCK_HANDLER,
        )
        assert f._knowledge_tool_schema is RETRIEVE_KNOWLEDGE_SCHEMA
        assert f._knowledge_tool_handler is _MOCK_HANDLER

    def test_reasoner_stores_knowledge_deps(self):
        r = Reasoner(
            client=_CLIENT,
            research_prefix="research/run-1",
            models_prefix="models/run-1",
            knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
            knowledge_tool_handler=_MOCK_HANDLER,
        )
        assert r._knowledge_tool_schema is RETRIEVE_KNOWLEDGE_SCHEMA
        assert r._knowledge_tool_handler is _MOCK_HANDLER

    def test_builder_stores_knowledge_deps(self):
        b = Builder(
            client=_CLIENT,
            models_prefix="models/run-1",
            project_root=Path("/tmp"),
            knowledge_tool_schema=RETRIEVE_KNOWLEDGE_SCHEMA,
            knowledge_tool_handler=_MOCK_HANDLER,
        )
        assert b._knowledge_tool_schema is RETRIEVE_KNOWLEDGE_SCHEMA
        assert b._knowledge_tool_handler is _MOCK_HANDLER

    def test_formalizer_no_knowledge_deps_by_default(self):
        f = Formalizer(
            client=_CLIENT,
            research_prefix="research/run-1",
        )
        assert f._knowledge_tool_schema is None
        assert f._knowledge_tool_handler is None

    def test_reasoner_no_knowledge_deps_by_default(self):
        r = Reasoner(
            client=_CLIENT,
            research_prefix="research/run-1",
            models_prefix="models/run-1",
        )
        assert r._knowledge_tool_schema is None
        assert r._knowledge_tool_handler is None

    def test_builder_no_knowledge_deps_by_default(self):
        b = Builder(
            client=_CLIENT,
            models_prefix="models/run-1",
            project_root=Path("/tmp"),
        )
        assert b._knowledge_tool_schema is None
        assert b._knowledge_tool_handler is None


# ── Router._knowledge_tool_kwargs ──


class TestRouterKnowledgeToolKwargs:
    """Test Router._knowledge_tool_kwargs graceful degradation."""

    def _make_router(self):
        from unittest.mock import patch

        from decisionlab.router import PipelineState, Router, Stage

        state = PipelineState(
            stage=Stage.RESEARCH,
            problem="test",
            reports_dir=Path("/tmp"),
            run_id="run-1",
        )
        with patch.object(Router, "_init_memory_agent", return_value=None):
            router = Router(
                client=_CLIENT,
                state=state,
                search=_SEARCH,
                project_root=Path("/tmp"),
            )
        return router

    def _mock_shared(self, *, kg=None, vectors=None, embeddings=None):
        """Create a mock shared module for inline `import shared`."""
        mock = AsyncMock()
        mock.kg = kg
        mock.vectors = vectors
        mock.embeddings = embeddings
        mock.db = None
        return mock

    def test_returns_empty_when_no_infra(self):
        import sys

        router = self._make_router()
        mock = self._mock_shared()
        orig = sys.modules.get("shared")
        sys.modules["shared"] = mock
        try:
            result = router._knowledge_tool_kwargs("researcher")
        finally:
            if orig is not None:
                sys.modules["shared"] = orig
            else:
                sys.modules.pop("shared", None)
        assert result == {}

    def test_returns_kwargs_when_infra_available(self):
        import sys

        mock_kg = AsyncMock()
        mock_vectors = AsyncMock()
        mock_embeddings = AsyncMock()

        router = self._make_router()
        mock = self._mock_shared(
            kg=mock_kg,
            vectors=mock_vectors,
            embeddings=mock_embeddings,
        )
        orig = sys.modules.get("shared")
        sys.modules["shared"] = mock
        try:
            result = router._knowledge_tool_kwargs("researcher")
        finally:
            if orig is not None:
                sys.modules["shared"] = orig
            else:
                sys.modules.pop("shared", None)

        assert "knowledge_tool_schema" in result
        assert "knowledge_tool_handler" in result
        assert result["knowledge_tool_schema"] is RETRIEVE_KNOWLEDGE_SCHEMA
        assert callable(result["knowledge_tool_handler"])

    def test_returns_empty_when_only_kg_available(self):
        """Partial infra (only kg) should still return kwargs since kg is not None."""
        import sys

        router = self._make_router()
        mock = self._mock_shared(kg=AsyncMock())
        orig = sys.modules.get("shared")
        sys.modules["shared"] = mock
        try:
            result = router._knowledge_tool_kwargs("researcher")
        finally:
            if orig is not None:
                sys.modules["shared"] = orig
            else:
                sys.modules.pop("shared", None)

        assert "knowledge_tool_schema" in result
        assert callable(result["knowledge_tool_handler"])

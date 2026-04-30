"""Tests for graceful degradation when knowledge infrastructure is unavailable (P4-004).

Covers:
- Startup degradation: services not running → singletons set to None
- Mid-run degradation: service crashes during pipeline → errors caught, pipeline continues
- Partial degradation: some services up, others down → independent degradation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SHARED_MODULE = "shared"
_TOOL_MODULE = "decisionlab.knowledge.retrieval.tool"
_KG_RETRIEVAL_MODULE = "decisionlab.knowledge.retrieval.kg_retrieval"
_VECTOR_MODULE = "decisionlab.knowledge.retrieval.vector_retrieval"
_MEMORY_AGENT_MODULE = "decisionlab.agents.memory_agent"


@pytest.fixture(autouse=True)
def _reset_shared_singletons():
    """Reset shared module-level singletons between tests."""
    import shared

    saved = (shared.storage, shared.db, shared.kg, shared.vectors, shared.embeddings)
    shared.storage = None
    shared.db = None
    shared.kg = None
    shared.vectors = None
    shared.embeddings = None
    yield
    shared.storage, shared.db, shared.kg, shared.vectors, shared.embeddings = saved


def _make_settings(**overrides):
    """Create a minimal Settings-like object for shared.init()."""
    defaults = {
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_ACCESS_KEY": "test",
        "MINIO_SECRET_KEY": "test",
        "S3_BUCKET": "test",
        "DATABASE_URL": "sqlite+aiosqlite:///test.db",
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
        "QDRANT_URL": "http://localhost:6333",
        "VOYAGE_API_KEY": "voy-test",
        "ZEROENTROPY_API_KEY": "ze-test",
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


# ═══════════════════════════════════════════════════════════════════════════
# 1. STARTUP DEGRADATION
# ═══════════════════════════════════════════════════════════════════════════


class TestStartupDegradation:
    """AC1: Pipeline starts successfully when knowledge infra is unavailable."""

    @pytest.mark.asyncio
    async def test_neo4j_down_sets_kg_to_none(self):
        """When Neo4j is unreachable, shared.kg stays None and init doesn't crash."""
        import shared

        settings = _make_settings()

        mock_storage = MagicMock()
        mock_storage.connect = AsyncMock()
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_vs = MagicMock()
        mock_vs.connect = AsyncMock()
        mock_vs.init_collections = AsyncMock()

        with (
            patch("shared.StorageService", return_value=mock_storage),
            patch("shared.DatabaseService", return_value=mock_db),
            patch("shared.KnowledgeGraph") as mock_kg_cls,
            patch("shared.VectorStore", return_value=mock_vs),
        ):
            mock_kg_instance = MagicMock()
            mock_kg_instance.init_schema = AsyncMock(
                side_effect=ConnectionRefusedError("Neo4j unavailable")
            )
            mock_kg_cls.return_value = mock_kg_instance

            await shared.init(settings)

        assert shared.kg is None
        assert shared.vectors is not None
        assert shared.embeddings is not None

    @pytest.mark.asyncio
    async def test_qdrant_down_sets_vectors_to_none(self):
        """When Qdrant is unreachable, shared.vectors stays None."""
        import shared

        settings = _make_settings()

        mock_storage = MagicMock()
        mock_storage.connect = AsyncMock()
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_kg = MagicMock()
        mock_kg.init_schema = AsyncMock()

        with (
            patch("shared.StorageService", return_value=mock_storage),
            patch("shared.DatabaseService", return_value=mock_db),
            patch("shared.KnowledgeGraph", return_value=mock_kg),
            patch("shared.VectorStore") as mock_vs_cls,
        ):
            mock_vs_instance = MagicMock()
            mock_vs_instance.connect = AsyncMock(
                side_effect=ConnectionRefusedError("Qdrant unavailable")
            )
            mock_vs_cls.return_value = mock_vs_instance

            await shared.init(settings)

        assert shared.kg is not None
        assert shared.vectors is None
        assert shared.embeddings is not None

    @pytest.mark.asyncio
    async def test_voyage_api_key_missing_sets_embeddings_to_none(self):
        """When Voyage AI key is missing, shared.embeddings stays None."""
        import shared

        settings = _make_settings(VOYAGE_API_KEY="", ZEROENTROPY_API_KEY="")

        mock_storage = MagicMock()
        mock_storage.connect = AsyncMock()
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_kg = MagicMock()
        mock_kg.init_schema = AsyncMock()
        mock_vs = MagicMock()
        mock_vs.connect = AsyncMock()
        mock_vs.init_collections = AsyncMock()

        with (
            patch("shared.StorageService", return_value=mock_storage),
            patch("shared.DatabaseService", return_value=mock_db),
            patch("shared.KnowledgeGraph", return_value=mock_kg),
            patch("shared.VectorStore", return_value=mock_vs),
        ):
            await shared.init(settings)

        assert shared.kg is not None
        assert shared.vectors is not None
        assert shared.embeddings is None

    @pytest.mark.asyncio
    async def test_all_knowledge_infra_down(self):
        """When all knowledge services are down, pipeline still starts."""
        import shared

        settings = _make_settings(VOYAGE_API_KEY="", ZEROENTROPY_API_KEY="")

        mock_storage = MagicMock()
        mock_storage.connect = AsyncMock()
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()

        with (
            patch("shared.StorageService", return_value=mock_storage),
            patch("shared.DatabaseService", return_value=mock_db),
            patch("shared.KnowledgeGraph") as mock_kg_cls,
            patch("shared.VectorStore") as mock_vs_cls,
        ):
            mock_kg_cls.return_value.init_schema = AsyncMock(
                side_effect=OSError("Neo4j down")
            )
            mock_vs_cls.return_value.connect = AsyncMock(
                side_effect=OSError("Qdrant down")
            )

            await shared.init(settings)

        assert shared.kg is None
        assert shared.vectors is None
        assert shared.embeddings is None
        # Core infra still works
        assert shared.storage is not None
        assert shared.db is not None

    @pytest.mark.asyncio
    async def test_degradation_warning_logged(self, caplog):
        """WARNING logged listing unavailable services."""
        import logging

        import shared

        settings = _make_settings(VOYAGE_API_KEY="")

        mock_storage = MagicMock()
        mock_storage.connect = AsyncMock()
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()

        with (
            patch("shared.StorageService", return_value=mock_storage),
            patch("shared.DatabaseService", return_value=mock_db),
            patch("shared.KnowledgeGraph") as mock_kg_cls,
            patch("shared.VectorStore") as mock_vs_cls,
        ):
            mock_kg_cls.return_value.init_schema = AsyncMock(
                side_effect=OSError("Neo4j down")
            )
            mock_vs_cls.return_value.connect = AsyncMock(
                side_effect=OSError("Qdrant down")
            )

            with caplog.at_level(logging.WARNING, logger="shared"):
                await shared.init(settings)

        assert "Running in degraded mode" in caplog.text


# ═══════════════════════════════════════════════════════════════════════════
# 2. MID-RUN DEGRADATION — retrieve_knowledge tool
# ═══════════════════════════════════════════════════════════════════════════


class TestToolMidRunDegradation:
    """AC4: retrieve_knowledge returns graceful message when services crash mid-run."""

    @pytest.mark.asyncio
    async def test_kg_crash_returns_graceful_message(self):
        """If Neo4j crashes mid-retrieval, tool returns fallback message."""
        from decisionlab.knowledge.retrieval.tool import create_retrieve_knowledge

        handler = create_retrieve_knowledge(
            kg=MagicMock(),
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            search_adapter=MagicMock(),
            client=AsyncMock(),
            run_id="run-1",
            stage="researcher",
        )

        with (
            patch(
                f"{_TOOL_MODULE}.kg_retrieve",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Neo4j connection lost"),
            ),
            patch(
                f"{_TOOL_MODULE}.vector_retrieve",
                new_callable=AsyncMock,
                return_value=([], []),
            ),
        ):
            result = await handler({"query": "test query"})

        assert "temporarily unavailable" in result.lower()

    @pytest.mark.asyncio
    async def test_qdrant_crash_returns_graceful_message(self):
        """If Qdrant crashes mid-retrieval, tool returns fallback message."""
        from decisionlab.knowledge.retrieval.tool import create_retrieve_knowledge

        handler = create_retrieve_knowledge(
            kg=MagicMock(),
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            search_adapter=MagicMock(),
            client=AsyncMock(),
            run_id="run-1",
            stage="researcher",
        )

        with (
            patch(
                f"{_TOOL_MODULE}.kg_retrieve",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                f"{_TOOL_MODULE}.vector_retrieve",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Qdrant connection lost"),
            ),
        ):
            result = await handler({"query": "test query"})

        assert "temporarily unavailable" in result.lower()

    @pytest.mark.asyncio
    async def test_voyage_crash_returns_graceful_message(self):
        """If Voyage AI is unreachable, tool returns fallback message."""
        from decisionlab.knowledge.retrieval.tool import create_retrieve_knowledge

        handler = create_retrieve_knowledge(
            kg=MagicMock(),
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            search_adapter=MagicMock(),
            client=AsyncMock(),
            run_id="run-1",
            stage="builder",
        )

        with (
            patch(
                f"{_TOOL_MODULE}.kg_retrieve",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Voyage AI 503"),
            ),
            patch(
                f"{_TOOL_MODULE}.vector_retrieve",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Voyage AI 503"),
            ),
        ):
            result = await handler({"query": "test query"})

        assert "temporarily unavailable" in result.lower()

    @pytest.mark.asyncio
    async def test_tool_never_raises(self):
        """The tool handler never raises — always returns a string."""
        from decisionlab.knowledge.retrieval.tool import create_retrieve_knowledge

        handler = create_retrieve_knowledge(
            kg=MagicMock(),
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            search_adapter=MagicMock(),
            client=AsyncMock(),
            run_id="run-1",
            stage="researcher",
        )

        with (
            patch(
                f"{_TOOL_MODULE}.kg_retrieve",
                new_callable=AsyncMock,
                side_effect=Exception("unexpected"),
            ),
            patch(
                f"{_TOOL_MODULE}.vector_retrieve",
                new_callable=AsyncMock,
                side_effect=Exception("unexpected"),
            ),
        ):
            result = await handler({"query": "test"})

        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════
# 3. MID-RUN DEGRADATION — Memory Agent
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoryAgentMidRunDegradation:
    """AC3: Memory Agent catches connection errors, returns empty result."""

    @pytest.mark.asyncio
    async def test_neo4j_crash_returns_zeroed_result(self):
        """If Neo4j crashes during KG population, Memory Agent continues."""
        from decisionlab.agents.memory_agent import MemoryAgent
        from decisionlab.knowledge.models import (
            ExtractionResult,
            MemoryAgentResult,
            NodeSpec,
        )

        agent = MemoryAgent(
            client=AsyncMock(),
            kg=MagicMock(),
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            db=MagicMock(),
        )

        extraction = ExtractionResult(
            nodes=[
                NodeSpec(
                    label="Paradigm", properties={"slug": "test"}, natural_key="slug"
                )
            ],
            relations=[],
            facts=["fact"],
            stage="researcher",
            run_id="run-1",
        )

        mock_db = MagicMock()
        session = AsyncMock()
        session.commit = AsyncMock()
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _get_session():
            yield session

        mock_db.get_session = _get_session
        agent._db = mock_db

        with (
            patch(
                f"{_MEMORY_AGENT_MODULE}.extract",
                new_callable=AsyncMock,
                return_value=extraction,
            ),
            patch(
                f"{_MEMORY_AGENT_MODULE}.populate_kg",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Neo4j crashed"),
            ),
            patch(
                f"{_MEMORY_AGENT_MODULE}.index_stage_output",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Qdrant crashed"),
            ),
            patch(
                f"{_MEMORY_AGENT_MODULE}.resolve_and_store",
                new_callable=AsyncMock,
                side_effect=ConnectionError("DB crashed"),
            ),
        ):
            result = await agent.run("researcher", "some text", "run-1")

        assert isinstance(result, MemoryAgentResult)
        assert result.nodes_created == 0

    @pytest.mark.asyncio
    async def test_run_never_raises(self):
        """Memory Agent.run() never raises, even on unexpected errors."""
        from decisionlab.agents.memory_agent import MemoryAgent
        from decisionlab.knowledge.models import MemoryAgentResult

        agent = MemoryAgent(
            client=AsyncMock(),
            kg=MagicMock(),
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            db=MagicMock(),
        )

        with patch(
            f"{_MEMORY_AGENT_MODULE}.extract",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Total failure"),
        ):
            result = await agent.run("researcher", "some text", "run-1")

        assert isinstance(result, MemoryAgentResult)
        assert result.nodes_created == 0
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_emit_failure_does_not_crash_run(self):
        """If the emit callback raises, run() still completes."""
        from decisionlab.agents.memory_agent import MemoryAgent
        from decisionlab.knowledge.models import (
            ExtractionResult,
            IndexResult,
            KGWriteResult,
            MemoryAgentResult,
            NodeSpec,
            ResolutionResult,
        )

        bad_emit = AsyncMock(side_effect=RuntimeError("WebSocket closed"))

        agent = MemoryAgent(
            client=AsyncMock(),
            kg=MagicMock(),
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            db=MagicMock(),
        )

        extraction = ExtractionResult(
            nodes=[
                NodeSpec(label="Paradigm", properties={"slug": "t"}, natural_key="slug")
            ],
            relations=[],
            facts=[],
            stage="researcher",
            run_id="run-1",
        )

        mock_db = MagicMock()
        session = AsyncMock()
        session.commit = AsyncMock()
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _get_session():
            yield session

        mock_db.get_session = _get_session
        agent._db = mock_db

        with (
            patch(
                f"{_MEMORY_AGENT_MODULE}.extract",
                new_callable=AsyncMock,
                return_value=extraction,
            ),
            patch(
                f"{_MEMORY_AGENT_MODULE}.populate_kg",
                new_callable=AsyncMock,
                return_value=KGWriteResult(
                    nodes_created=1,
                    nodes_merged=0,
                    relations_created=0,
                    relations_superseded=0,
                ),
            ),
            patch(
                f"{_MEMORY_AGENT_MODULE}.index_stage_output",
                new_callable=AsyncMock,
                return_value=IndexResult(
                    artifacts_indexed=1, facts_indexed=0, total_chunks=1
                ),
            ),
            patch(
                f"{_MEMORY_AGENT_MODULE}.resolve_and_store",
                new_callable=AsyncMock,
                return_value=ResolutionResult(
                    memories_created=0,
                    duplicates_skipped=0,
                    corroborations=0,
                    enrichments=0,
                    contradictions=0,
                    sonnet_calls=0,
                ),
            ),
        ):
            result = await agent.run("researcher", "text", "run-1", emit=bad_emit)

        assert isinstance(result, MemoryAgentResult)


# ═══════════════════════════════════════════════════════════════════════════
# 4. PARTIAL DEGRADATION
# ═══════════════════════════════════════════════════════════════════════════


class TestPartialDegradation:
    """AC5: Individual subsystems degrade independently."""

    @pytest.mark.asyncio
    async def test_kg_down_qdrant_up_kg_retrieve_returns_empty(self):
        """When Neo4j crashes mid-run, kg_retrieve returns [] not an exception."""
        from decisionlab.knowledge.retrieval.kg_retrieval import kg_retrieve

        mock_kg = MagicMock()
        mock_kg.query = AsyncMock(side_effect=ConnectionError("Neo4j down"))

        mock_embedding = MagicMock()
        mock_client = AsyncMock()
        # _extract_entities needs a response
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                type="text", text='{"entities": [{"name": "test", "type": "paradigm"}]}'
            )
        ]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        result = await kg_retrieve("test query", mock_kg, mock_embedding, mock_client)

        assert result == []

    @pytest.mark.asyncio
    async def test_qdrant_down_neo4j_up_vector_retrieve_returns_empty(self):
        """When Qdrant crashes mid-run, vector_retrieve returns ([], [])."""
        from decisionlab.knowledge.retrieval.vector_retrieval import vector_retrieve

        mock_embedding = MagicMock()
        mock_embedding.embed_query = AsyncMock(
            side_effect=ConnectionError("Voyage AI down")
        )
        mock_vs = MagicMock()

        result = await vector_retrieve("test query", mock_embedding, mock_vs)

        assert result == ([], [])

    @pytest.mark.asyncio
    async def test_tool_partial_neo4j_down_vector_works(self):
        """Neo4j down but Qdrant up: tool returns vector results, not error."""
        from decisionlab.knowledge.retrieval.models import CRAGResult, RetrievalResult
        from decisionlab.knowledge.retrieval.tool import create_retrieve_knowledge

        vec_result = RetrievalResult(
            text="Vector result from Qdrant",
            score=0.9,
            source="dense",
            metadata={"namespace": "paradigm"},
        )
        crag = CRAGResult(results=[vec_result], action="pass_through")

        handler = create_retrieve_knowledge(
            kg=MagicMock(),
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            search_adapter=MagicMock(),
            client=AsyncMock(),
            run_id="run-1",
            stage="researcher",
        )

        with (
            patch(
                f"{_TOOL_MODULE}.kg_retrieve",
                new_callable=AsyncMock,
                return_value=[],  # KG returns empty (connection issue caught internally)
            ),
            patch(
                f"{_TOOL_MODULE}.vector_retrieve",
                new_callable=AsyncMock,
                return_value=([vec_result], []),
            ),
            patch(
                f"{_TOOL_MODULE}.fuse_and_rerank",
                new_callable=AsyncMock,
                return_value=[vec_result],
            ),
            patch(
                f"{_TOOL_MODULE}.evaluate_results",
                new_callable=AsyncMock,
                return_value=crag,
            ),
        ):
            result = await handler({"query": "test"})

        assert "Retrieved Knowledge" in result
        assert "Vector result from Qdrant" in result
        assert "temporarily unavailable" not in result.lower()

    @pytest.mark.asyncio
    async def test_memory_agent_partial_neo4j_down_indexing_works(self):
        """Neo4j down: Memory Agent skips KG but indexing still runs."""
        from decisionlab.agents.memory_agent import MemoryAgent
        from decisionlab.knowledge.models import (
            ExtractionResult,
            IndexResult,
            NodeSpec,
            ResolutionResult,
        )

        agent = MemoryAgent(
            client=AsyncMock(),
            kg=MagicMock(),
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            db=MagicMock(),
        )

        extraction = ExtractionResult(
            nodes=[
                NodeSpec(
                    label="Paradigm", properties={"slug": "test"}, natural_key="slug"
                )
            ],
            relations=[],
            facts=["fact"],
            stage="researcher",
            run_id="run-1",
        )

        mock_db = MagicMock()
        session = AsyncMock()
        session.commit = AsyncMock()
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _get_session():
            yield session

        mock_db.get_session = _get_session
        agent._db = mock_db

        idx_result = IndexResult(artifacts_indexed=3, facts_indexed=1, total_chunks=4)

        with (
            patch(
                f"{_MEMORY_AGENT_MODULE}.extract",
                new_callable=AsyncMock,
                return_value=extraction,
            ),
            patch(
                f"{_MEMORY_AGENT_MODULE}.populate_kg",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Neo4j crashed"),
            ),
            patch(
                f"{_MEMORY_AGENT_MODULE}.index_stage_output",
                new_callable=AsyncMock,
                return_value=idx_result,
            ) as m_idx,
            patch(
                f"{_MEMORY_AGENT_MODULE}.resolve_and_store",
                new_callable=AsyncMock,
                return_value=ResolutionResult(
                    memories_created=1,
                    duplicates_skipped=0,
                    corroborations=0,
                    enrichments=0,
                    contradictions=0,
                    sonnet_calls=0,
                ),
            ),
        ):
            result = await agent.run("researcher", "output text", "run-1")

        # Indexing still ran despite KG failure
        m_idx.assert_awaited_once()
        # KG results zeroed, but facts_stored from resolution
        assert result.nodes_created == 0
        assert result.facts_stored == 1


# ═══════════════════════════════════════════════════════════════════════════
# 5. AC6: No unhandled exceptions
# ═══════════════════════════════════════════════════════════════════════════


class TestNoUnhandledExceptions:
    """AC6: All errors are caught and logged — no unhandled exceptions."""

    @pytest.mark.asyncio
    async def test_kg_retrieve_never_raises(self):
        """kg_retrieve catches all exceptions, returns []."""
        from decisionlab.knowledge.retrieval.kg_retrieval import kg_retrieve

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=Exception("API totally down")
        )

        result = await kg_retrieve("query", MagicMock(), MagicMock(), mock_client)
        assert result == []

    @pytest.mark.asyncio
    async def test_vector_retrieve_never_raises(self):
        """vector_retrieve catches all exceptions, returns ([], [])."""
        from decisionlab.knowledge.retrieval.vector_retrieval import vector_retrieve

        mock_embedding = MagicMock()
        mock_embedding.embed_query = AsyncMock(
            side_effect=Exception("Embedding service down")
        )
        mock_vs = MagicMock()

        result = await vector_retrieve("query", mock_embedding, mock_vs)
        assert result == ([], [])

    @pytest.mark.asyncio
    async def test_tool_handler_never_raises_to_agent_loop(self):
        """The tool handler always returns a string, never propagates exceptions."""
        from decisionlab.knowledge.retrieval.tool import create_retrieve_knowledge

        handler = create_retrieve_knowledge(
            kg=MagicMock(),
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            search_adapter=MagicMock(),
            client=AsyncMock(),
            run_id="run-1",
            stage="researcher",
        )

        # Simulate every downstream function failing
        with (
            patch(
                f"{_TOOL_MODULE}.kg_retrieve",
                new_callable=AsyncMock,
                side_effect=Exception("boom"),
            ),
            patch(
                f"{_TOOL_MODULE}.vector_retrieve",
                new_callable=AsyncMock,
                side_effect=Exception("boom"),
            ),
        ):
            result = await handler({"query": "test"})

        assert isinstance(result, str)
        assert "temporarily unavailable" in result.lower()

    @pytest.mark.asyncio
    async def test_memory_agent_run_never_raises(self):
        """MemoryAgent.run() always returns a MemoryAgentResult."""
        from decisionlab.agents.memory_agent import MemoryAgent
        from decisionlab.knowledge.models import MemoryAgentResult

        agent = MemoryAgent(
            client=AsyncMock(),
            kg=MagicMock(),
            vector_store=MagicMock(),
            embedding_service=MagicMock(),
            db=MagicMock(),
        )

        # extract raises unexpectedly
        with patch(
            f"{_MEMORY_AGENT_MODULE}.extract",
            new_callable=AsyncMock,
            side_effect=Exception("Catastrophic failure"),
        ):
            result = await agent.run("researcher", "text", "run-1")

        assert isinstance(result, MemoryAgentResult)
        assert result.nodes_created == 0

"""Tests for knowledge infrastructure lifecycle (Neo4j + Qdrant)."""
from unittest.mock import AsyncMock, patch

import pytest

import shared
from shared.knowledge_graph import KnowledgeGraph
from shared.vector_store import VectorStore
from shared.storage import StorageService
from shared.database import DatabaseService


@pytest.fixture
def _mock_core_services():
    """Mock Postgres + MinIO so tests don't need Docker running."""
    with (
        patch.object(StorageService, "connect", new_callable=AsyncMock),
        patch.object(StorageService, "close", new_callable=AsyncMock),
        patch.object(DatabaseService, "connect", new_callable=AsyncMock),
        patch.object(DatabaseService, "close", new_callable=AsyncMock),
    ):
        yield


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_core_services")
async def test_graceful_degradation_neo4j():
    """init() succeeds with warning when Neo4j is unreachable; knowledge_graph is None."""
    await shared.shutdown()
    with patch.object(KnowledgeGraph, "connect", new_callable=AsyncMock, side_effect=Exception("neo4j down")):
        await shared.init()
        try:
            assert shared.storage is not None
            assert shared.db is not None
            assert shared.knowledge_graph is None
        finally:
            await shared.shutdown()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_core_services")
async def test_graceful_degradation_qdrant():
    """init() succeeds with warning when Qdrant is unreachable; vector_store is None."""
    await shared.shutdown()
    with patch.object(VectorStore, "connect", new_callable=AsyncMock, side_effect=Exception("qdrant down")):
        await shared.init()
        try:
            assert shared.storage is not None
            assert shared.db is not None
            assert shared.vector_store is None
        finally:
            await shared.shutdown()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_core_services")
async def test_graceful_degradation_both():
    """init() succeeds when both Neo4j and Qdrant are unreachable."""
    await shared.shutdown()
    with (
        patch.object(KnowledgeGraph, "connect", new_callable=AsyncMock, side_effect=Exception("neo4j down")),
        patch.object(VectorStore, "connect", new_callable=AsyncMock, side_effect=Exception("qdrant down")),
    ):
        await shared.init()
        try:
            assert shared.storage is not None
            assert shared.db is not None
            assert shared.knowledge_graph is None
            assert shared.vector_store is None
        finally:
            await shared.shutdown()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_core_services")
async def test_init_connects_knowledge_services():
    """init() wires up knowledge_graph and vector_store when services are available."""
    await shared.shutdown()
    with (
        patch.object(KnowledgeGraph, "connect", new_callable=AsyncMock),
        patch.object(VectorStore, "connect", new_callable=AsyncMock),
    ):
        await shared.init()
        try:
            assert isinstance(shared.knowledge_graph, KnowledgeGraph)
            assert isinstance(shared.vector_store, VectorStore)
        finally:
            with (
                patch.object(KnowledgeGraph, "close", new_callable=AsyncMock),
                patch.object(VectorStore, "close", new_callable=AsyncMock),
            ):
                await shared.shutdown()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_core_services")
async def test_shutdown_closes_knowledge_services():
    """shutdown() closes knowledge_graph and vector_store and sets to None."""
    await shared.shutdown()
    with (
        patch.object(KnowledgeGraph, "connect", new_callable=AsyncMock),
        patch.object(VectorStore, "connect", new_callable=AsyncMock),
    ):
        await shared.init()
    with (
        patch.object(KnowledgeGraph, "close", new_callable=AsyncMock) as kg_close,
        patch.object(VectorStore, "close", new_callable=AsyncMock) as vs_close,
    ):
        await shared.shutdown()
        kg_close.assert_awaited_once()
        vs_close.assert_awaited_once()
    assert shared.knowledge_graph is None
    assert shared.vector_store is None


def test_knowledge_graph_not_connected_raises():
    """Accessing driver before connect() raises RuntimeError."""
    from shared.settings import load_settings
    kg = KnowledgeGraph(load_settings())
    with pytest.raises(RuntimeError, match="not connected"):
        kg.driver


def test_vector_store_not_connected_raises():
    """Accessing client before connect() raises RuntimeError."""
    from shared.settings import load_settings
    vs = VectorStore(load_settings())
    with pytest.raises(RuntimeError, match="not connected"):
        vs.client

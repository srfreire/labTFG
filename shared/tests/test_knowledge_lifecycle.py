"""Tests for knowledge infrastructure lifecycle (Neo4j + Qdrant)."""

from unittest.mock import AsyncMock, patch

import pytest

from shared.database import DatabaseService
from shared.knowledge_graph import KnowledgeGraph
from shared.services import init_services, shutdown_services
from shared.storage import StorageService
from shared.vector_store import VectorStore

pytestmark = pytest.mark.integration


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
    """init_services() succeeds with warning when Neo4j is unreachable; kg is None."""
    with (
        patch.object(
            KnowledgeGraph,
            "init_schema",
            new_callable=AsyncMock,
            side_effect=Exception("neo4j down"),
        ),
        patch.object(
            VectorStore,
            "connect",
            new_callable=AsyncMock,
        ),
        patch.object(
            VectorStore,
            "init_collections",
            new_callable=AsyncMock,
        ),
    ):
        services = await init_services()
        try:
            assert services.storage is not None
            assert services.db is not None
            assert services.kg is None
        finally:
            with patch.object(VectorStore, "close", new_callable=AsyncMock):
                await shutdown_services(services)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_core_services")
async def test_graceful_degradation_qdrant():
    """init_services() succeeds with warning when Qdrant is unreachable; vectors is None."""
    with (
        patch.object(
            KnowledgeGraph,
            "init_schema",
            new_callable=AsyncMock,
        ),
        patch.object(
            KnowledgeGraph,
            "close",
            new_callable=AsyncMock,
        ),
        patch.object(
            VectorStore,
            "connect",
            new_callable=AsyncMock,
            side_effect=Exception("qdrant down"),
        ),
    ):
        services = await init_services()
        try:
            assert services.storage is not None
            assert services.db is not None
            assert services.vectors is None
        finally:
            await shutdown_services(services)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_core_services")
async def test_graceful_degradation_both():
    """init_services() succeeds when both Neo4j and Qdrant are unreachable."""
    with (
        patch.object(
            KnowledgeGraph,
            "init_schema",
            new_callable=AsyncMock,
            side_effect=Exception("neo4j down"),
        ),
        patch.object(
            VectorStore,
            "connect",
            new_callable=AsyncMock,
            side_effect=Exception("qdrant down"),
        ),
    ):
        services = await init_services()
        try:
            assert services.storage is not None
            assert services.db is not None
            assert services.kg is None
            assert services.vectors is None
        finally:
            await shutdown_services(services)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_core_services")
async def test_init_connects_knowledge_services():
    """init_services() wires up kg and vectors when services are available."""
    with (
        patch.object(
            KnowledgeGraph,
            "init_schema",
            new_callable=AsyncMock,
        ),
        patch.object(
            KnowledgeGraph,
            "close",
            new_callable=AsyncMock,
        ),
        patch.object(
            VectorStore,
            "connect",
            new_callable=AsyncMock,
        ),
        patch.object(
            VectorStore,
            "init_collections",
            new_callable=AsyncMock,
        ),
        patch.object(
            VectorStore,
            "close",
            new_callable=AsyncMock,
        ),
    ):
        services = await init_services()
        try:
            assert isinstance(services.kg, KnowledgeGraph)
            assert isinstance(services.vectors, VectorStore)
        finally:
            await shutdown_services(services)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_core_services")
async def test_shutdown_closes_knowledge_services():
    """shutdown_services() closes kg and vectors."""
    with (
        patch.object(
            KnowledgeGraph,
            "init_schema",
            new_callable=AsyncMock,
        ),
        patch.object(
            VectorStore,
            "connect",
            new_callable=AsyncMock,
        ),
        patch.object(
            VectorStore,
            "init_collections",
            new_callable=AsyncMock,
        ),
    ):
        services = await init_services()
    with (
        patch.object(KnowledgeGraph, "close", new_callable=AsyncMock) as kg_close,
        patch.object(VectorStore, "close", new_callable=AsyncMock) as vs_close,
    ):
        await shutdown_services(services)
        kg_close.assert_awaited_once()
        vs_close.assert_awaited_once()


def test_vector_store_not_connected_raises():
    """Calling methods before connect() raises RuntimeError."""
    from shared.settings import load_settings

    vs = VectorStore(load_settings())
    with pytest.raises(RuntimeError, match="not connected"):
        vs._c()


def test_storage_service_not_connected_raises():
    """Calling methods before connect() raises RuntimeError."""
    from shared.settings import load_settings

    storage = StorageService(load_settings())
    with pytest.raises(RuntimeError, match="not connected"):
        storage._c()

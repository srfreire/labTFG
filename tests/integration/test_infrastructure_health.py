"""Bare-metal infrastructure health checks for docker-compose services."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from shared.knowledge_graph import KnowledgeGraph

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Postgres connectivity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_postgres_connects_and_queries(db_service):
    """The DatabaseService can open a session and execute SELECT 1."""
    async with db_service.get_session() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_postgres_create_tables_idempotent(engine):
    """Creating the schema twice is a no-op."""
    from shared.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Second call must not raise
        await conn.run_sync(Base.metadata.create_all)


# ---------------------------------------------------------------------------
# MinIO connectivity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_minio_put_get_delete(storage_service, unique_prefix):
    key = f"{unique_prefix}health.txt"
    await storage_service.put_text(key, "ok")
    assert await storage_service.get_text(key) == "ok"
    await storage_service.delete(key)
    assert await storage_service.exists(key) is False


# ---------------------------------------------------------------------------
# Neo4j connectivity and APOC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_neo4j_connectivity_and_constraints(kg_service: KnowledgeGraph):
    """init_schema creates at least one constraint on a known label."""
    results = await kg_service.query(
        "SHOW CONSTRAINTS YIELD name, labelsOrTypes, properties RETURN name"
    )
    names = {r["name"] for r in results}
    assert any("Paradigm" in n or "Paper" in n or "Postulate" in n for n in names)


@pytest.mark.asyncio
async def test_neo4j_apoc_plugin_available(kg_service: KnowledgeGraph):
    """APOC plugin is loaded — `apoc.version()` returns a string."""
    results = await kg_service.query("RETURN apoc.version() AS v")
    assert len(results) == 1
    assert isinstance(results[0]["v"], str)


# ---------------------------------------------------------------------------
# Qdrant connectivity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qdrant_connectivity_and_collections(vector_store):
    """Managed collections exist after init_collections."""
    client = vector_store._c()
    names = {c.name for c in (await client.get_collections()).collections}
    for expected in ("memories_dense", "memories_sparse"):
        assert expected in names


@pytest.mark.asyncio
async def test_qdrant_dense_and_sparse_insert(vector_store):
    """A single round-trip for both dense and sparse channels works."""
    import uuid as _uuid

    pid = str(_uuid.uuid4())
    payload = {
        "entity_id": _uuid.uuid4().hex,
        "namespace": "paradigm",
        "source_stage": "researcher",
        "run_id": _uuid.uuid4().hex,
        "importance": 5.0,
        "confidence": 0.8,
        "created_at": "2026-04-14T00:00:00Z",
        "text_preview": "health check",
    }
    vec = [0.0] * 1024
    vec[0] = 1.0

    await vector_store.upsert_dense("memories_dense", pid, vec, payload)
    hits_dense = await vector_store.search_dense("memories_dense", vec, limit=3)
    assert any(h.id == pid for h in hits_dense)

    sparse_id = str(_uuid.uuid4())
    await vector_store.upsert_sparse(
        "memories_sparse", sparse_id, "dopamine reward prediction", payload
    )
    hits_sparse = await vector_store.search_sparse(
        "memories_sparse", "dopamine", limit=3
    )
    assert any(h.id == sparse_id for h in hits_sparse)

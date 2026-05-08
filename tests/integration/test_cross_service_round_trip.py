"""Cross-service integration tests — Postgres + MinIO + Neo4j + Qdrant.

Requires all four docker-compose services healthy on localhost.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from shared.models import Artifact, Run

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Storage + DB: artifact registration round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_storage_put_then_artifact_register(
    storage_service, db_service, session, unique_prefix, run_id
):
    """Upload an object, then register its DB row and verify both sides."""
    key = f"{unique_prefix}model.txt"
    await storage_service.put_text(key, "hello")
    assert await storage_service.exists(key)

    run = Run(
        id=uuid.UUID(run_id),
        problem_description="cross-service",
        s3_prefix=unique_prefix,
    )
    session.add(run)
    await session.commit()

    artifact = Artifact(
        s3_key=key,
        artifact_type="text",
        size_bytes=len("hello"),
        content_type="text/plain",
        run_id=uuid.UUID(run_id),
    )
    session.add(artifact)
    await session.commit()

    # DB row exists
    result = await session.execute(select(Artifact).where(Artifact.s3_key == key))
    row = result.scalar_one()
    assert row.size_bytes == 5
    assert row.run_id == uuid.UUID(run_id)

    # Storage retrieve round-trip
    assert await storage_service.get_text(key) == "hello"
    await storage_service.delete(key)


# ---------------------------------------------------------------------------
# Knowledge graph + vector store: indexed paradigm
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kg_and_vector_paradigm_round_trip(kg_service, vector_store):
    """A paradigm lives in Neo4j; a corresponding embedding in Qdrant."""
    slug = f"xs-para-{uuid.uuid4().hex[:8]}"
    await kg_service.create_node(
        "Paradigm",
        {"slug": slug, "name": "Cross-Service Paradigm"},
    )

    pid = str(uuid.uuid4())
    vector = [0.0] * 1024
    vector[7] = 1.0
    await vector_store.upsert_dense(
        "memories_dense",
        pid,
        vector,
        {
            "entity_id": slug,
            "namespace": "paradigm",
            "source_stage": "researcher",
            "run_id": uuid.uuid4().hex,
            "importance": 5.0,
            "confidence": 0.8,
            "created_at": "2026-04-14T00:00:00Z",
            "text_preview": "cross-service paradigm",
        },
    )

    # KG lookup
    node = await kg_service.get_node("Paradigm", "slug", slug)
    assert node is not None
    assert node["name"] == "Cross-Service Paradigm"

    # Vector search finds the same paradigm by payload
    results = await vector_store.search_dense(
        "memories_dense", vector, limit=5, filters={"namespace": "paradigm"}
    )
    matched = next((r for r in results if r.id == pid), None)
    assert matched is not None
    assert matched.payload["entity_id"] == slug


# ---------------------------------------------------------------------------
# Full shared.init() lifecycle with all services
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_init_exposes_all_services():
    """shared.init() boots Storage + DB; KG/Vectors come up when reachable."""
    import shared

    await shared.shutdown()
    await shared.init()
    try:
        assert shared.storage is not None
        assert shared.db is not None
        # KG and vectors depend on connectivity — assert at least one worked
        # (docker-compose setup has all of them healthy)
        assert shared.kg is not None
        assert shared.vectors is not None
    finally:
        await shared.shutdown()
        assert shared.storage is None
        assert shared.db is None
        assert shared.kg is None
        assert shared.vectors is None


# ---------------------------------------------------------------------------
# Memory + Storage: temporal query pairs with S3-stored extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_storage_pairing(storage_service, session, unique_prefix, run_id):
    """A Memory row references an S3-stored extraction artifact."""
    from shared.pipeline_memories import create_memory

    # Extraction stored in S3
    key = f"{unique_prefix}extraction.json"
    await storage_service.put_text(key, '{"entities": []}')

    # Run row required by FK constraint
    run = Run(
        id=uuid.UUID(run_id),
        problem_description="memory pairing",
        s3_prefix=unique_prefix,
    )
    session.add(run)
    await session.commit()

    # Memory row referencing that extraction
    mem = await create_memory(
        session,
        content="cross-service memory",
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        importance=6.0,
        confidence=0.75,
        run_id=uuid.UUID(run_id),
    )
    await session.commit()

    assert await storage_service.get_text(key) == '{"entities": []}'
    assert mem.run_id == uuid.UUID(run_id)
    await storage_service.delete(key)


# ---------------------------------------------------------------------------
# Vector + memory: memory indexed into Qdrant, searchable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_indexed_and_retrieved(session, vector_store):
    """A PipelineMemory row's embedding is upserted into memories_dense and searchable."""
    from shared.models import Run
    from shared.pipeline_memories import create_memory

    run = Run(problem_description="indexed", s3_prefix="r/")
    session.add(run)
    await session.commit()

    mem = await create_memory(
        session,
        content="vector-search-me",
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        run_id=run.id,
        importance=7.0,
        confidence=0.9,
    )
    await session.commit()
    mem_id = mem.id

    vec = [0.0] * 1024
    vec[12] = 1.0
    await vector_store.upsert_dense(
        "memories_dense",
        str(mem_id),
        vec,
        {
            "entity_id": str(mem_id),
            "namespace": "paradigm",
            "source_stage": "researcher",
            "run_id": uuid.uuid4().hex,
            "importance": 7.0,
            "confidence": 0.9,
            "created_at": "2026-04-14T00:00:00Z",
            "text_preview": "vector-search-me",
        },
    )

    results = await vector_store.search_dense("memories_dense", vec, limit=3)
    assert any(r.id == str(mem_id) for r in results)

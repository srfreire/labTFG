"""Integration test: PG and Neo4j agree on relations valid at *as_of* (P4-004).

Exercises the two-step ``KnowledgeGraph.query_at_time`` against real
Postgres + Neo4j services brought up by ``shared.init()``.  Asserts that
for a multi-version dataset the set of relations Neo4j returns for an
``as_of`` checkpoint matches the set of ``pipeline_memories`` rows live
at that checkpoint — i.e. the source of truth (PG) and its index (Neo4j)
never disagree about who was valid when.

Skipped automatically when the docker-compose services aren't running
(see the ``shared.init`` degraded-mode warning).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Load Phase 1's .env before importing `shared.settings` so service
# credentials match docker-compose. Without this the default
# NEO4J_PASSWORD in shared.settings.py is wrong and shared.init() fails
# silently into degraded mode.
try:
    from dotenv import load_dotenv

    _ENV = Path(__file__).resolve().parent.parent / ".env"
    if _ENV.exists():
        load_dotenv(_ENV, override=False)
except ImportError:
    pass

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy import text as sql_text

import shared
from shared.knowledge_graph import (
    KG_RELATION_NAMESPACE,
    fetch_memory_temporal_meta,
    select_valid_memory_ids,
)
from shared.models import PipelineMemory, Run

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


_PARADIGM_SLUG = "p4004-temporal-consistency"


@pytest_asyncio.fixture
async def shared_infra():
    """Bring up real shared infra and require KG + DB to be wired."""
    await shared.init()
    if shared.kg is None or shared.db is None:
        await shared.shutdown()
        pytest.skip("docker-compose Neo4j/Postgres unavailable")
    try:
        yield shared
    finally:
        await shared.shutdown()


async def _seed_paradigm() -> None:
    assert shared.kg is not None
    await shared.kg.query(
        "MERGE (p:Paradigm {slug: $slug}) "
        "ON CREATE SET p.name = 'P4-004 Temporal Test', "
        "p.description = 'Synthetic paradigm for temporal-consistency assertions'",
        {"slug": _PARADIGM_SLUG},
    )


async def _create_run(session) -> uuid.UUID:
    run = Run(
        problem_description="P4-004 temporal consistency",
        s3_prefix=f"_xs/p4004/{uuid.uuid4().hex}",
    )
    session.add(run)
    await session.flush()
    await session.commit()
    return run.id


async def _insert_relation_version(
    session,
    *,
    run_id: uuid.UUID,
    rel_index: int,
    valid_from: datetime,
    valid_to: datetime | None = None,
    confidence: float = 0.7,
) -> uuid.UUID:
    """Insert one PG row + one Neo4j edge linked by memory_id."""
    new_id = uuid.uuid4()
    naive_valid_from = valid_from.replace(tzinfo=None)
    naive_valid_to = valid_to.replace(tzinfo=None) if valid_to is not None else None

    mem = PipelineMemory(
        id=new_id,
        content=f"Postulate.test-v{rel_index} -[BELONGS_TO]-> "
        f"Paradigm.{_PARADIGM_SLUG}",
        namespace=KG_RELATION_NAMESPACE,
        memory_type="semantic",
        source_stage="test",
        run_id=run_id,
        importance=5.0,
        confidence=confidence,
        valid_from=naive_valid_from,
        valid_to=naive_valid_to,
    )
    session.add(mem)
    await session.flush()
    await session.commit()

    assert shared.kg is not None
    postulate_id = f"{_PARADIGM_SLUG}:v-{new_id.hex[:8]}"
    await shared.kg.query(
        "MERGE (p:Postulate {id: $pid}) "
        "ON CREATE SET p.statement = 'synthetic test postulate'",
        {"pid": postulate_id},
    )
    await shared.kg.query(
        "MATCH (a:Postulate {id: $pid}), (b:Paradigm {slug: $slug}) "
        "CREATE (a)-[r:BELONGS_TO {memory_id: $memory_id}]->(b)",
        {
            "pid": postulate_id,
            "slug": _PARADIGM_SLUG,
            "memory_id": str(new_id),
        },
    )
    return new_id


@pytest_asyncio.fixture
async def temporal_dataset(shared_infra):
    """Build a 4-version dataset spanning a year.

    Versions:
      v0: valid 2025-01-01 → 2025-04-01 (superseded)
      v1: valid 2025-04-01 → 2025-08-01 (superseded)
      v2: valid 2025-08-01 → 2025-12-01 (superseded)
      v3: valid 2025-12-01 → ∞          (live)
    """
    async with shared.db.get_session() as session:
        await _seed_paradigm()
        run_id = await _create_run(session)

        base = datetime(2025, 1, 1, tzinfo=UTC)
        boundaries = [
            base,
            base + timedelta(days=90),
            base + timedelta(days=210),
            base + timedelta(days=330),
            None,
        ]

        versions: list[uuid.UUID] = []
        for i in range(4):
            versions.append(
                await _insert_relation_version(
                    session,
                    run_id=run_id,
                    rel_index=i,
                    valid_from=boundaries[i],  # type: ignore[arg-type]
                    valid_to=boundaries[i + 1],
                    confidence=0.5 + 0.1 * i,
                )
            )

    yield {"run_id": run_id, "versions": versions}

    async with shared.db.get_session() as session:
        await session.execute(
            delete(PipelineMemory).where(PipelineMemory.id.in_(versions))
        )
        await session.execute(
            sql_text("DELETE FROM runs WHERE id = :id"), {"id": run_id}
        )
        await session.commit()
    await shared.kg.query(
        "MATCH (p:Paradigm {slug: $slug}) DETACH DELETE p",
        {"slug": _PARADIGM_SLUG},
    )
    await shared.kg.query(
        "MATCH (n:Postulate) WHERE n.id STARTS WITH $prefix DETACH DELETE n",
        {"prefix": f"{_PARADIGM_SLUG}:v-"},
    )


async def _kg_memory_ids_at(*, session, as_of: datetime) -> set[str]:
    rows = await shared.kg.query_at_time(
        f"MATCH (a:Postulate)-[r:BELONGS_TO]->(b:Paradigm {{slug: '{_PARADIGM_SLUG}'}}) "
        "RETURN r.memory_id AS memory_id",
        as_of=as_of,
        session=session,
    )
    return {row["memory_id"] for row in rows if row.get("memory_id")}


async def _pg_memory_ids_at(*, session, as_of: datetime) -> set[str]:
    return set(await select_valid_memory_ids(session, as_of))


# ---------------------------------------------------------------------------
# AC4: PG and KG agree at every checkpoint
# ---------------------------------------------------------------------------


async def test_at_each_boundary_pg_and_kg_agree(temporal_dataset):
    """For four evenly-spaced checkpoints, the set of valid memory_ids is
    the same whether we read from PG (source) or via ``query_at_time``."""
    versions = temporal_dataset["versions"]
    owned = {str(v) for v in versions}

    base = datetime(2025, 1, 1, tzinfo=UTC)
    checkpoints = [base + timedelta(days=d) for d in (45, 150, 270, 365)]

    async with shared.db.get_session() as session:
        for as_of in checkpoints:
            pg_ids = await _pg_memory_ids_at(session=session, as_of=as_of)
            kg_ids = await _kg_memory_ids_at(session=session, as_of=as_of)
            assert pg_ids & owned == kg_ids & owned, (
                f"PG/KG mismatch at {as_of.isoformat()}: "
                f"pg={pg_ids & owned} kg={kg_ids & owned}"
            )


async def test_active_version_at_end_of_timeline(temporal_dataset):
    """The live version at the very end of the timeline is exactly v3."""
    versions = temporal_dataset["versions"]
    owned = {str(v) for v in versions}
    final = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=400)
    expected = {str(versions[3])}

    async with shared.db.get_session() as session:
        pg_ids = await _pg_memory_ids_at(session=session, as_of=final)
        kg_ids = await _kg_memory_ids_at(session=session, as_of=final)
    assert pg_ids & owned == expected
    assert kg_ids & owned == expected


async def test_query_at_time_includes_seed_relations(shared_infra):
    """Pre-P4-004 relations (no memory_id) survive ``query_at_time`` always."""
    seed_paradigm = f"{_PARADIGM_SLUG}-seed"
    seed_postulate = f"{seed_paradigm}:seed"
    try:
        await shared.kg.query(
            "MERGE (p:Paradigm {slug: $slug}) ON CREATE SET p.name = 'seed'",
            {"slug": seed_paradigm},
        )
        await shared.kg.query(
            "MERGE (q:Postulate {id: $pid}) ON CREATE SET q.statement = 'seed'",
            {"pid": seed_postulate},
        )
        await shared.kg.query(
            "MATCH (a:Postulate {id: $pid}), (b:Paradigm {slug: $slug}) "
            "CREATE (a)-[r:BELONGS_TO]->(b)",
            {"pid": seed_postulate, "slug": seed_paradigm},
        )

        as_of = datetime(2024, 1, 1, tzinfo=UTC)
        async with shared.db.get_session() as session:
            rows = await shared.kg.query_at_time(
                f"MATCH (a:Postulate {{id: '{seed_postulate}'}})"
                f"-[r:BELONGS_TO]->(b:Paradigm {{slug: '{seed_paradigm}'}}) "
                "RETURN r.memory_id AS memory_id",
                as_of=as_of,
                session=session,
            )
        assert any(row.get("memory_id") is None for row in rows), (
            "expected the seed edge (no memory_id) to pass the temporal filter"
        )
    finally:
        await shared.kg.query(
            "MATCH (n:Paradigm {slug: $slug}) DETACH DELETE n",
            {"slug": seed_paradigm},
        )
        await shared.kg.query(
            "MATCH (n:Postulate {id: $pid}) DETACH DELETE n",
            {"pid": seed_postulate},
        )


async def test_fetch_memory_temporal_meta_matches_pg(temporal_dataset):
    """``fetch_memory_temporal_meta`` returns the same row PG holds."""
    versions = temporal_dataset["versions"]
    async with shared.db.get_session() as session:
        meta = await fetch_memory_temporal_meta(session, [str(v) for v in versions])
    assert set(meta) == {str(v) for v in versions}
    assert meta[str(versions[3])]["valid_to"] is None
    assert meta[str(versions[0])]["valid_to"] is not None
    confidences = [meta[str(v)]["confidence"] for v in versions]
    assert confidences == sorted(confidences)

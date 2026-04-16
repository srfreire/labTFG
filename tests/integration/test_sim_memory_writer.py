"""Integration — TrackerMemoryWriter against real Postgres + Qdrant + Voyage.

Migrated from phase2-juan/tests/knowledge/test_integration.py to reuse the
shared fixtures in `tests/conftest.py`. Runs with `pytest -m integration`;
requires docker-compose services healthy and Voyage/ZeroEntropy keys set.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import delete, select

from shared.embedding import EmbeddingService
from shared.models import Memory
from simlab.knowledge import (
    ModelInfo,
    SimulationContext,
    TrackerMemoryWriter,
)

pytestmark = pytest.mark.integration


def _skip_if_no_keys() -> None:
    if not os.environ.get("VOYAGE_API_KEY") or not os.environ.get("ZEROENTROPY_API_KEY"):
        pytest.skip("VOYAGE_API_KEY and ZEROENTROPY_API_KEY required for integration tests")


@pytest.mark.asyncio
async def test_writer_round_trip_postgres_and_qdrant(
    settings, db_service, vector_store, session,
):
    """Write memories for a fake simulation and verify both stores + cleanup."""
    _skip_if_no_keys()

    embeddings = EmbeddingService(
        voyage_api_key=settings.VOYAGE_API_KEY,
        zeroentropy_api_key=settings.ZEROENTROPY_API_KEY,
    )
    writer = TrackerMemoryWriter(
        vector_store=vector_store,
        embedding_service=embeddings,
        db=db_service,
    )

    experiment_id = f"itest-{uuid.uuid4()}"
    model = ModelInfo(
        model_id=str(uuid.uuid4()),
        class_name="IntegrationTestModel",
        paradigm="integration-test-paradigm",
        formulation="integration-test-formulation",
        phase1_run_id=None,
    )
    context = SimulationContext(
        phase2_experiment_id=experiment_id,
        environment="integration-grid-5x5",
        steps=50,
        seed=1,
        agent_to_model={"agent_0": model},
    )
    tracker = {
        "summary": "Integration test agent explored the grid and starved at step 45.",
        "trajectories": {
            "agent_0": {
                "steps_survived": 45,
                "resources_consumed": 2,
                "actions": {"move_east": 20, "move_west": 15, "consume": 2},
            },
        },
        "episodes": [
            {
                "agent": "agent_0",
                "type": "starvation",
                "step": 45,
                "description": "Agent depleted its energy reserves.",
            },
        ],
    }

    result = await writer.write(json.dumps(tracker), context)

    try:
        assert result.skipped_reason is None
        assert result.summaries_written == 1
        assert result.trajectories_written == 1
        assert result.episodes_written == 1

        # Postgres check — 3 rows with correct namespace/stage/confidence/memory_type.
        stmt = select(Memory).where(
            Memory.metadata_["phase2_experiment_id"].astext == experiment_id
        )
        rows = (await session.execute(stmt)).scalars().all()

        assert len(rows) == 3
        assert {r.namespace for r in rows} == {"simulation"}
        assert {r.source_stage for r in rows} == {"tracker"}
        assert all(r.confidence == pytest.approx(0.80) for r in rows)

        by_type: dict[str, int] = {}
        for r in rows:
            by_type[r.memory_type] = by_type.get(r.memory_type, 0) + 1
        assert by_type == {"semantic": 2, "episodic": 1}

        # Qdrant check — our UUIDs are retrievable via dense search.
        query_vec = await embeddings.embed_query(
            "agent starvation in integration grid"
        )
        hits = await vector_store.search_dense(
            "memories_dense",
            query_vec,
            limit=20,
            filters={"phase2_experiment_id": experiment_id},
        )
        hit_ids = {h.id for h in hits}
        row_ids = {str(r.id) for r in rows}
        assert hit_ids.issuperset(row_ids), (
            f"Expected all {len(row_ids)} memories in Qdrant; got {len(hit_ids & row_ids)}"
        )

    finally:
        # Cleanup Postgres rows
        await session.execute(
            delete(Memory).where(
                Memory.metadata_["phase2_experiment_id"].astext == experiment_id
            )
        )
        await session.commit()

        # Cleanup Qdrant points
        try:
            qdrant_ids = [str(r.id) for r in rows]
            if qdrant_ids:
                await vector_store.delete("memories_dense", qdrant_ids)
                await vector_store.delete("memories_sparse", qdrant_ids)
        except Exception:
            pass

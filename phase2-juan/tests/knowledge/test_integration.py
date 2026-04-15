"""P1-004 — integration test with real Postgres + Qdrant + Voyage.

Marked `@pytest.mark.integration`; skipped by default. Run with:

    uv run pytest tests/knowledge/test_integration.py -m integration

Requires:
- docker-compose up with Postgres + Qdrant listening on the URLs in .env.
- VOYAGE_API_KEY and ZEROENTROPY_API_KEY set in the environment.
- Alembic migrations applied (memories table exists).
- Qdrant `memories_dense` / `memories_sparse` collections initialised
  (the writer's factory does this via `VectorStore.init_collections`).
"""
from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import delete, select

from shared.models import Memory
from shared.settings import load_settings
from simlab.knowledge import (
    ModelInfo,
    SimulationContext,
    build_writer_from_settings,
)

pytestmark = pytest.mark.integration


def _skip_if_no_keys():
    if not os.environ.get("VOYAGE_API_KEY") or not os.environ.get("ZEROENTROPY_API_KEY"):
        pytest.skip("VOYAGE_API_KEY and ZEROENTROPY_API_KEY required for integration tests")


async def test_end_to_end_write_and_retrieve():
    _skip_if_no_keys()

    settings = load_settings()
    writer = await build_writer_from_settings(settings)
    if writer is None:
        pytest.skip("build_writer_from_settings returned None — infra unavailable")

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

    # ------------------------------------------------------------------ write
    result = await writer.write(json.dumps(tracker), context)

    try:
        assert result.skipped_reason is None
        assert result.summaries_written == 1
        assert result.trajectories_written == 1
        assert result.episodes_written == 1

        # ---------------------------------------------------- Postgres check
        async with writer._db.get_session() as session:
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

        # -------------------------------------------------------- Qdrant check
        query_vec = await writer._embeddings.embed_query(
            "agent starvation in integration grid"
        )
        hits = await writer._vectors.search_dense(
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
        # ---------------------------------------------------- Cleanup Postgres
        async with writer._db.get_session() as session:
            await session.execute(
                delete(Memory).where(
                    Memory.metadata_["phase2_experiment_id"].astext == experiment_id
                )
            )
            await session.commit()

        # ---------------------------------------------------- Cleanup Qdrant
        qdrant_ids = [str(r.id) for r in rows] if rows else []
        if qdrant_ids:
            try:
                await writer._vectors.delete("memories_dense", qdrant_ids)
                await writer._vectors.delete("memories_sparse", qdrant_ids)
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass

        await writer._db.close()
        await writer._vectors.close()

"""E2E — sim-memory cross-phase loop.

Validates the closed loop: Phase 2's TrackerMemoryWriter writes a simulation
observation, then Phase 1's hybrid retrieval (dense + sparse) finds it when
queried for the matching paradigm/formulation.

This is the only test that exercises the **contract** between the two
phases: metadata field names (`phase2_experiment_id`, `paradigm`, ...),
confidence/namespace conventions, and UUID coherence across Postgres
and Qdrant.

Real infra required (@pytest.mark.e2e), mocked LLM — no Voyage credits
spent beyond embeddings for 3 short facts.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from simlab.knowledge import (
    ModelInfo,
    SimulationContext,
    TrackerMemoryWriter,
)
from sqlalchemy import delete, select

from shared.embedding import EmbeddingService
from shared.models import Memory

pytestmark = pytest.mark.e2e


def _skip_if_no_keys() -> None:
    if not os.environ.get("VOYAGE_API_KEY") or not os.environ.get(
        "ZEROENTROPY_API_KEY"
    ):
        pytest.skip("VOYAGE_API_KEY and ZEROENTROPY_API_KEY required for e2e tests")


@pytest.mark.asyncio
async def test_tracker_write_is_retrievable_by_paradigm_filter(
    settings,
    db_service,
    vector_store,
    session,
):
    """After writing, a dense-search filtered by paradigm should surface our memories."""
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

    # --- Phase 2 side: simulate a completed run and write its observations ---
    experiment_id = f"e2e-{uuid.uuid4()}"
    paradigm_slug = f"e2e-paradigm-{uuid.uuid4().hex[:8]}"
    model = ModelInfo(
        model_id=str(uuid.uuid4()),
        class_name="E2EModel",
        paradigm=paradigm_slug,
        formulation="e2e-formulation",
        phase1_run_id=None,
    )
    context = SimulationContext(
        phase2_experiment_id=experiment_id,
        environment="e2e-grid-8x8",
        steps=60,
        seed=7,
        agent_to_model={"agent_0": model},
    )
    tracker_json = json.dumps(
        {
            "summary": f"E2E agent explored under paradigm {paradigm_slug} and starved.",
            "trajectories": {
                "agent_0": {
                    "steps_survived": 60,
                    "resources_consumed": 3,
                    "actions": {"move_east": 25, "consume": 3},
                },
            },
            "episodes": [
                {
                    "agent": "agent_0",
                    "type": "starvation",
                    "step": 60,
                    "description": "Agent exhausted resources mid-exploration.",
                },
            ],
        }
    )

    write_result = await writer.write(tracker_json, context)
    assert write_result.skipped_reason is None
    assert (
        write_result.summaries_written
        + write_result.trajectories_written
        + write_result.episodes_written
        == 3
    )

    rows: list[Memory] = []
    try:
        # --- Phase 1 side: simulate the Builder retrieving prior sim observations ---
        # The Phase-1 retrieval layer (retrieve_knowledge) would dispatch dense +
        # sparse + KG search in parallel and fuse with RRF. For the e2e contract
        # test we inline the dense channel to keep infra minimal.
        query = "models failing by starvation in a grid environment"
        query_vec = await embeddings.embed_query(query)

        hits = await vector_store.search_dense(
            "memories_dense",
            query_vec,
            limit=20,
            filters={"paradigm": paradigm_slug},
        )
        assert len(hits) >= 1, (
            "Phase-1-style retrieval by paradigm found nothing; "
            "the write/read contract is broken."
        )

        # Every payload matches the expected contract (Phase 1 can rely on these keys).
        for hit in hits:
            assert hit.payload["namespace"] == "simulation"
            assert hit.payload["paradigm"] == paradigm_slug
            assert hit.payload["formulation"] == "e2e-formulation"
            assert hit.payload["model_class_name"] == "E2EModel"
            assert hit.payload["phase2_experiment_id"] == experiment_id

        # Sparse contract: BM25 on model class_name should also match.
        from shared.tokenizer import tokenize_to_sparse

        sp_indices, sp_values = tokenize_to_sparse("E2EModel starvation")
        sparse_hits = await vector_store.search_sparse(
            "memories_sparse",
            sp_indices,
            sp_values,
            limit=20,
            filters={"paradigm": paradigm_slug},
        )
        assert len(sparse_hits) >= 1, "Sparse channel missed the memories"

        # --- Cross-store join via UUID ---
        stmt = select(Memory).where(
            Memory.metadata_["phase2_experiment_id"].astext == experiment_id
        )
        rows = list((await session.execute(stmt)).scalars().all())
        row_ids = {str(r.id) for r in rows}
        hit_ids = {h.id for h in hits}
        assert row_ids.issubset(hit_ids), (
            "UUIDs from Postgres do not match the dense-hit IDs — "
            "the shared-UUID contract is broken."
        )

    finally:
        await session.execute(
            delete(Memory).where(
                Memory.metadata_["phase2_experiment_id"].astext == experiment_id
            )
        )
        await session.commit()

        qdrant_ids = [str(r.id) for r in rows]
        if qdrant_ids:
            try:
                await vector_store.delete("memories_dense", qdrant_ids)
                await vector_store.delete("memories_sparse", qdrant_ids)
            except Exception:
                pass

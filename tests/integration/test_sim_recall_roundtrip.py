"""Integration — sim-memory write → sim-recall read roundtrip.

Demonstrates the cross-feature contract: TrackerMemoryWriter (sim-memory)
writes simulation observations to the Knowledge Backbone, and
retrieve_context (sim-recall) reads them back.

Runs with ``pytest -m integration``; requires docker-compose services
healthy and Voyage/ZeroEntropy keys set.
"""
from __future__ import annotations

import json
import os
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import delete

import shared
from shared.embedding import EmbeddingService
from shared.models import Memory
from simlab.knowledge import ModelInfo, SimulationContext, TrackerMemoryWriter
from simlab.recall.retrieve import retrieve_context

pytestmark = pytest.mark.integration


def _skip_if_no_keys() -> None:
    if not os.environ.get("VOYAGE_API_KEY") or not os.environ.get("ZEROENTROPY_API_KEY"):
        pytest.skip("VOYAGE_API_KEY and ZEROENTROPY_API_KEY required for integration tests")


@pytest.mark.asyncio
async def test_write_then_retrieve_roundtrip(
    settings, db_service, vector_store, session, kg_service,
):
    """Write memories via TrackerMemoryWriter, then read back via retrieve_context."""
    _skip_if_no_keys()

    # -- Setup: wire shared singletons so retrieve_context can find infra --
    shared.vectors = vector_store
    shared.kg = kg_service
    shared.embeddings = EmbeddingService(
        voyage_api_key=settings.VOYAGE_API_KEY,
        zeroentropy_api_key=settings.ZEROENTROPY_API_KEY,
    )
    shared.db = db_service

    paradigm_slug = f"recall-e2e-{uuid.uuid4().hex[:8]}"

    # -- Step 1: Write via sim-memory --
    writer = TrackerMemoryWriter(
        vector_store=vector_store,
        embedding_service=shared.embeddings,
        db=db_service,
    )
    model = ModelInfo(
        model_id=str(uuid.uuid4()),
        class_name="RoundtripTestModel",
        paradigm=paradigm_slug,
        formulation=f"{paradigm_slug}-formulation",
        phase1_run_id=None,
    )
    context = SimulationContext(
        phase2_experiment_id=f"roundtrip-{uuid.uuid4().hex[:8]}",
        environment="roundtrip-grid-5x5",
        steps=50,
        seed=42,
        agent_to_model={"agent_0": model},
    )
    tracker_json = json.dumps({
        "summary": f"Agent survived 50 steps under {paradigm_slug} paradigm. Resources stable.",
        "trajectories": {
            "agent_0": {
                "steps_survived": 50,
                "resources_consumed": 12,
                "actions": {"move_up": 20, "move_right": 15, "consume": 15},
            },
        },
        "episodes": [
            {"agent": "agent_0", "type": "resource_found", "step": 10, "description": "Found resource at (3,2)"},
            {"agent": "agent_0", "type": "resource_found", "step": 25, "description": "Found resource at (4,3)"},
            {"agent": "agent_0", "type": "resource_found", "step": 40, "description": "Found resource at (2,4)"},
        ],
    })

    result = await writer.write(tracker_json, context)
    assert result.skipped_reason is None, f"Writer skipped: {result.skipped_reason}"
    assert result.summaries_written > 0

    # -- Step 2: Read via sim-recall (flag forced ON via env override) --
    from dataclasses import replace
    flag_on = replace(settings, ENABLE_KNOWLEDGE_READ=True)

    try:
        with patch("simlab.recall.retrieve.load_settings", return_value=flag_on):
            retrieved = await retrieve_context(
                query=f"simulation results for {paradigm_slug}",
                namespace="simulation",
                top_k=5,
            )

        # -- Step 3: Verify the roundtrip --
        assert "Retrieved Knowledge" in retrieved
        assert "(0 results)" not in retrieved, f"Expected results but got: {retrieved}"
        assert paradigm_slug in retrieved, f"Paradigm slug not found in: {retrieved}"

    finally:
        await session.execute(delete(Memory).where(Memory.content.contains(paradigm_slug)))
        await session.commit()

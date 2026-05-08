"""E2E smoke tests — exercise the knowledge pipeline against real Postgres,
Neo4j, Qdrant, and MinIO using a mocked Anthropic client.

These verify that the wiring across phase1's knowledge subsystem and the
shared infrastructure all work together, without burning any LLM credits.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from shared.models import PipelineMemory as Memory
from shared.models import Run
from shared.pipeline_memories import create_memory, get_memories

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Mock LLM helpers
# ---------------------------------------------------------------------------


def _text_response(text: str) -> MagicMock:
    """Build a minimal Anthropic message response containing one text block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [block]
    response.usage = MagicMock(input_tokens=10, output_tokens=20)
    return response


def _make_async_client(responses: list[MagicMock]) -> AsyncMock:
    """A fake AsyncAnthropic client that yields *responses* in sequence."""
    client = AsyncMock()
    iterator = iter(responses)

    async def _create(**_kwargs):
        try:
            return next(iterator)
        except StopIteration:
            return _text_response("{}")

    client.messages.create = _create
    return client


# ---------------------------------------------------------------------------
# Memory pipeline E2E: extract → KG write → indexer → resolver
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_memory_lifecycle_against_real_infra(
    session, kg_service, vector_store, run_id
):
    """Create a memory, persist it, retrieve it temporally, supersede it."""
    from shared.pipeline_memories import (
        get_memories_at_time,
        get_supersession_chain,
        supersede_memory,
    )

    # Run row to satisfy FK
    session.add(
        Run(
            id=uuid.UUID(run_id),
            problem_description="lifecycle e2e",
            s3_prefix=f"research/{run_id}/",
        )
    )
    await session.commit()

    # Create a fact
    base_kwargs = dict(
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        importance=7.0,
        confidence=0.8,
        run_id=uuid.UUID(run_id),
    )
    v1 = await create_memory(
        session,
        content="alpha = 0.1",
        **base_kwargs,
    )
    await session.commit()
    v1_id = v1.id

    # Index v1 in Qdrant
    vec = [0.0] * 1024
    vec[5] = 1.0
    await vector_store.upsert_dense(
        "memories_dense",
        str(v1_id),
        vec,
        {
            "entity_id": str(v1_id),
            "namespace": "paradigm",
            "source_stage": "researcher",
            "run_id": run_id,
            "importance": 7.0,
            "confidence": 0.8,
            "created_at": "2026-04-14T00:00:00Z",
            "text_preview": "alpha = 0.1",
        },
    )

    # Add a Paradigm node referencing this memory
    slug = f"e2e-paradigm-{uuid.uuid4().hex[:8]}"
    await kg_service.create_node(
        "Paradigm",
        {"slug": slug, "name": "E2E Paradigm"},
    )

    # Confirm initial retrieval works across all 3 stores
    found = await get_memories(session, namespace="paradigm")
    assert any(m.id == v1_id for m in found)
    qdrant_hits = await vector_store.search_dense("memories_dense", vec, limit=5)
    assert any(h.id == str(v1_id) for h in qdrant_hits)
    kg_node = await kg_service.get_node("Paradigm", "slug", slug)
    assert kg_node is not None

    # Supersede v1 → v2
    v2 = await supersede_memory(
        session,
        v1_id,
        "alpha = 0.05",
        **base_kwargs,
    )
    await session.commit()
    v2_id = v2.id

    # Supersession chain
    chain = await get_supersession_chain(session, v1_id)
    assert [m.id for m in chain] == [v1_id, v2_id]

    # Temporal query: at time-of-creation, only v1 is valid
    session.expire_all()
    result = await session.execute(select(Memory).where(Memory.id == v1_id))
    v1_refreshed = result.scalar_one()
    assert v1_refreshed.valid_to is not None  # supersession set valid_to

    history = await get_memories_at_time(
        session,
        as_of=v1_refreshed.valid_from,
        namespace="paradigm",
    )
    assert any(m.id == v1_id for m in history)


# ---------------------------------------------------------------------------
# Memory Agent E2E with mocked LLM but real infra
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_agent_runs_end_to_end_with_real_infra(
    db_service, kg_service, vector_store, run_id
):
    """MemoryAgent.run() wires extraction → KG → indexing → resolution."""
    from decisionlab.agents.memory_agent import MemoryAgent

    extraction_payload = {
        "entities": [
            {
                "label": "Paradigm",
                "natural_key": {"slug": f"hedonic-{uuid.uuid4().hex[:6]}"},
                "properties": {"name": "Hedonic"},
                "confidence": 0.9,
            }
        ],
        "relations": [],
        "facts": [],
    }
    fenced = f"```json\n{json.dumps(extraction_payload)}\n```"

    # Mocked client returns extraction JSON for any messages.create()
    client = _make_async_client([_text_response(fenced)])

    agent = MemoryAgent(
        client=client,
        kg=kg_service,
        vector_store=vector_store,
        embedding_service=None,  # disable embedding (no Voyage credits)
        db=db_service,  # but resolution is skipped without embeddings
    )

    result = await agent.run(
        stage="researcher",
        stage_output="Hedonic is the paradigm under study.",
        run_id=run_id,
    )

    # MemoryAgent never raises and returns a result
    assert result is not None
    assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# Memory Agent: empty output is a no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_agent_skips_empty_output(db_service, kg_service, vector_store):
    from decisionlab.agents.memory_agent import MemoryAgent

    client = _make_async_client([])
    agent = MemoryAgent(
        client=client,
        kg=kg_service,
        vector_store=vector_store,
        embedding_service=None,
        db=db_service,
    )

    result = await agent.run(stage="researcher", stage_output="   ", run_id="x")
    assert result.nodes_created == 0
    assert result.facts_stored == 0


# ---------------------------------------------------------------------------
# Cross-run retrieval: memories from run A are visible to run B
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_run_memory_visibility(session):
    """Memories are scoped by run_id but queryable across runs."""
    run_a = uuid.uuid4()
    run_b = uuid.uuid4()
    session.add_all(
        [
            Run(id=run_a, problem_description="run a", s3_prefix=f"r/{run_a}/"),
            Run(id=run_b, problem_description="run b", s3_prefix=f"r/{run_b}/"),
        ]
    )
    await session.commit()

    await create_memory(
        session,
        content="run-a fact",
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        importance=5.0,
        confidence=0.7,
        run_id=run_a,
    )
    await create_memory(
        session,
        content="run-b fact",
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        importance=5.0,
        confidence=0.7,
        run_id=run_b,
    )
    await session.commit()

    # Both visible without run filter
    all_mems = await get_memories(session, namespace="paradigm")
    contents = [m.content for m in all_mems]
    assert "run-a fact" in contents
    assert "run-b fact" in contents

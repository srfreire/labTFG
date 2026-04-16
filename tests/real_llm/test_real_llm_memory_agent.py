"""Real-LLM end-to-end test for `decisionlab.agents.memory_agent.MemoryAgent`.

Runs the full deterministic pipeline (extract → KG write → vector indexing →
resolve) against a real LLM, real Postgres, real Neo4j, real Qdrant, and real
Voyage/ZeroEntropy. The most expensive test in the suite.
"""

from __future__ import annotations

import uuid

import pytest

from decisionlab.agents.memory_agent import MemoryAgent

SHORT_OUTPUT = """\
# Decision-making paradigms: foraging in mice

## 1. Homeostatic regulation
Drive reduction theory: animals act to reduce internal needs.
**Key authors**: Cannon (1932)
**Key concepts**: set point, negative feedback, drive

## References
- Cannon (1932) - The Wisdom of the Body
"""


@pytest.mark.asyncio
async def test_real_memory_agent_full_pipeline(
    real_anthropic_client,
    real_embedding_service,
    db_service,
    kg_service,
    vector_store,
):
    """Run MemoryAgent end-to-end and assert it doesn't raise + produces a result."""
    run_id = str(uuid.uuid4())
    agent = MemoryAgent(
        client=real_anthropic_client,
        kg=kg_service,
        vector_store=vector_store,
        embedding_service=real_embedding_service,
        db=db_service,
    )

    result = await agent.run(
        stage="researcher",
        stage_output=SHORT_OUTPUT,
        run_id=run_id,
    )

    # MemoryAgent never raises; it returns a counts result
    assert result is not None
    assert result.duration_ms > 0


@pytest.mark.asyncio
async def test_real_memory_agent_empty_output_skips(
    real_anthropic_client,
    real_embedding_service,
    db_service,
    kg_service,
    vector_store,
):
    """Empty stage output short-circuits before any LLM call."""
    agent = MemoryAgent(
        client=real_anthropic_client,
        kg=kg_service,
        vector_store=vector_store,
        embedding_service=real_embedding_service,
        db=db_service,
    )
    result = await agent.run(stage="researcher", stage_output="", run_id="e")
    assert result.nodes_created == 0
    assert result.facts_stored == 0

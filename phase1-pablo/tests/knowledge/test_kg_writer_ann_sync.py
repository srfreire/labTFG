"""kg_writer writes ``n.embedding`` to Neo4j after writing slug-like
nodes — replacing the prior Qdrant ``kg_entities_dense`` upsert.

Embeddings are passed in via the ``embeddings`` keyword (post-P4-001
DI). The KG itself is mocked through ``execute_write`` and ``query``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.knowledge import kg_writer as w
from decisionlab.knowledge.models import ExtractionResult, NodeSpec


def _ext(nodes):
    return ExtractionResult(
        nodes=nodes, relations=[], facts=[], stage="researcher", run_id="r1"
    )


@pytest.mark.asyncio
async def test_paradigm_write_triggers_embedding_set():
    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(return_value=[[0.1] * 1024])

    fake_kg = MagicMock()
    fake_kg.execute_write = AsyncMock(return_value={"was_created": True})
    fake_kg.unique_key_for = MagicMock(return_value="slug")
    fake_kg.query = AsyncMock(return_value=[])

    extraction = _ext(
        [
            NodeSpec(
                label="Paradigm",
                properties={
                    "slug": "rl",
                    "name": "Reinforcement Learning",
                    "description": "RL paradigm",
                },
                natural_key="slug",
            )
        ]
    )

    await w.populate_kg(extraction, fake_kg, embeddings=fake_emb)

    fake_emb.embed_texts.assert_awaited_once()
    fake_kg.query.assert_awaited_once()
    cypher, params = fake_kg.query.await_args.args
    assert "SET n.embedding = $vector" in cypher
    assert "MATCH (n:Paradigm" in cypher
    assert "{slug:" in cypher
    assert params["key_value"] == "rl"
    assert params["vector"] == [0.1] * 1024


@pytest.mark.asyncio
async def test_non_slug_label_does_not_trigger_embedding_set():
    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(return_value=[[0.1] * 1024])

    fake_kg = MagicMock()
    fake_kg.execute_write = AsyncMock(return_value={"was_created": True})
    fake_kg.unique_key_for = MagicMock(return_value="doi")
    fake_kg.query = AsyncMock(return_value=[])

    extraction = _ext(
        [
            NodeSpec(
                label="Paper",
                properties={"doi": "10.1/x", "title": "X"},
                natural_key="doi",
            )
        ]
    )

    await w.populate_kg(extraction, fake_kg, embeddings=fake_emb)
    fake_kg.query.assert_not_awaited()


@pytest.mark.asyncio
async def test_embedding_failure_does_not_break_write():
    """If Voyage is down, the KG write should still complete cleanly —
    embedding sync is best-effort."""
    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(side_effect=RuntimeError("voyage down"))

    fake_kg = MagicMock()
    fake_kg.execute_write = AsyncMock(return_value={"was_created": True})
    fake_kg.unique_key_for = MagicMock(return_value="slug")
    fake_kg.query = AsyncMock(return_value=[])

    extraction = _ext(
        [
            NodeSpec(
                label="Paradigm",
                properties={"slug": "rl", "name": "RL", "description": "."},
                natural_key="slug",
            )
        ]
    )

    result = await w.populate_kg(extraction, fake_kg, embeddings=fake_emb)
    # Write succeeded; embedding failure logged but not surfaced as an error.
    assert result.nodes_created == 1

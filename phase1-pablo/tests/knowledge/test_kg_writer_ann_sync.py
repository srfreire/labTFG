<<<<<<< HEAD
"""kg_writer writes ``n.embedding`` to Neo4j after writing slug-like
nodes — replacing the prior Qdrant ``kg_entities_dense`` upsert.

Test seam: kg_writer reads the embedding service via a helper func
that the test monkeypatches. The KG itself is mocked through
``execute_write`` and ``query``.
=======
"""kg_writer upserts into kg_entities_dense after writing slug-like nodes —
so the entity ANN index stays current with the graph.
>>>>>>> strike/infra-P4-001
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
<<<<<<< HEAD
async def test_paradigm_write_triggers_embedding_set(monkeypatch):
=======
async def test_paradigm_write_triggers_ann_upsert():
>>>>>>> strike/infra-P4-001
    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(return_value=[[0.1] * 1024])

    fake_kg = MagicMock()
    fake_kg.execute_write = AsyncMock(return_value={"was_created": True})
    fake_kg.unique_key_for = MagicMock(return_value="slug")
    fake_kg.query = AsyncMock(return_value=[])

<<<<<<< HEAD
    monkeypatch.setattr(w, "_get_embedding_service", lambda: fake_emb)

=======
>>>>>>> strike/infra-P4-001
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

    await w.populate_kg(extraction, fake_kg, embeddings=fake_emb, vectors=fake_vec)

    fake_emb.embed_texts.assert_awaited_once()
    fake_kg.query.assert_awaited_once()
    cypher, params = fake_kg.query.await_args.args
    assert "SET n.embedding = $vector" in cypher
    assert "MATCH (n:Paradigm" in cypher
    assert "{slug:" in cypher
    assert params["key_value"] == "rl"
    assert params["vector"] == [0.1] * 1024


@pytest.mark.asyncio
<<<<<<< HEAD
async def test_non_slug_label_does_not_trigger_embedding_set(monkeypatch):
=======
async def test_non_slug_label_does_not_trigger_ann_upsert():
>>>>>>> strike/infra-P4-001
    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(return_value=[[0.1] * 1024])

    fake_kg = MagicMock()
    fake_kg.execute_write = AsyncMock(return_value={"was_created": True})
    fake_kg.unique_key_for = MagicMock(return_value="doi")
    fake_kg.query = AsyncMock(return_value=[])

<<<<<<< HEAD
    monkeypatch.setattr(w, "_get_embedding_service", lambda: fake_emb)

=======
>>>>>>> strike/infra-P4-001
    extraction = _ext(
        [
            NodeSpec(
                label="Paper",
                properties={"doi": "10.1/x", "title": "X"},
                natural_key="doi",
            )
        ]
    )

<<<<<<< HEAD
    await w.populate_kg(extraction, fake_kg)
    fake_kg.query.assert_not_awaited()


@pytest.mark.asyncio
async def test_embedding_failure_does_not_break_write(monkeypatch):
    """If Voyage is down, the KG write should still complete cleanly —
    embedding sync is best-effort."""
=======
    await w.populate_kg(extraction, fake_kg, embeddings=fake_emb, vectors=fake_vec)
    fake_vec.upsert_dense.assert_not_awaited()


@pytest.mark.asyncio
async def test_ann_failure_does_not_break_write():
    """If Qdrant is down, the KG write should still complete cleanly — ANN
    sync is best-effort."""
>>>>>>> strike/infra-P4-001
    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(side_effect=RuntimeError("voyage down"))

    fake_kg = MagicMock()
    fake_kg.execute_write = AsyncMock(return_value={"was_created": True})
    fake_kg.unique_key_for = MagicMock(return_value="slug")
    fake_kg.query = AsyncMock(return_value=[])

<<<<<<< HEAD
    monkeypatch.setattr(w, "_get_embedding_service", lambda: fake_emb)

=======
>>>>>>> strike/infra-P4-001
    extraction = _ext(
        [
            NodeSpec(
                label="Paradigm",
                properties={"slug": "rl", "name": "RL", "description": "."},
                natural_key="slug",
            )
        ]
    )

<<<<<<< HEAD
    result = await w.populate_kg(extraction, fake_kg)
    # Write succeeded; embedding failure logged but not surfaced as an error.
=======
    result = await w.populate_kg(
        extraction, fake_kg, embeddings=fake_emb, vectors=fake_vec
    )
    # Write succeeded; ANN failure logged but not surfaced as an error.
>>>>>>> strike/infra-P4-001
    assert result.nodes_created == 1

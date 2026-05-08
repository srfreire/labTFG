"""Vector-index entity linking — replaces the prior Qdrant
``kg_entities_dense`` round-trip with a single Cypher
``db.index.vector.queryNodes`` call against the label's native Neo4j
vector index (P4-002).

Ordering inside _link_entities:
    1. Exact case-insensitive match on the label's name property.
    2. ANN against the label's native Neo4j vector index.
    3. (no fallback to table scan — that path is deleted).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.knowledge.retrieval import kg_retrieval as kg_r


@pytest.mark.asyncio
async def test_link_entities_falls_through_to_ann_when_no_exact_match(monkeypatch):
    """When the case-insensitive Cypher exact match returns nothing,
    _link_entities should call _link_entities_ann."""
    called = AsyncMock(
        return_value=[
            kg_r._LinkedEntity(
                node_id="el-1",
                label="Paradigm",
                name="Reinforcement Learning",
                confidence=0.91,
            )
        ]
    )
    monkeypatch.setattr(kg_r, "_link_entities_ann", called)

    fake_kg = MagicMock()
    fake_kg.query = AsyncMock(return_value=[])  # no exact match
    fake_emb = MagicMock()

    out = await kg_r._link_entities(
        [{"name": "RL", "type": "paradigm"}], fake_kg, fake_emb
    )
    called.assert_awaited_once()
    assert out[0].name == "Reinforcement Learning"


@pytest.mark.asyncio
async def test_ann_below_threshold_returns_empty():
    """If best vector hit is below the similarity threshold, return [] —
    no fallback to table scan."""
    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    fake_kg = MagicMock()
    fake_kg.query = AsyncMock(
        return_value=[{"id": "el-low", "name": "Foo", "score": 0.50}]
    )

    out = await kg_r._link_entities_ann("Paradigm", "FooQuery", fake_emb, fake_kg)
    assert out == []
    fake_kg.query.assert_awaited_once()


@pytest.mark.asyncio
async def test_ann_above_threshold_returns_linked_entity():
    """Above-threshold vector hit returns elementId + display name from
    the same Cypher call — no second hop needed."""
    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    fake_kg = MagicMock()
    fake_kg.query = AsyncMock(
        return_value=[
            {"id": "el-42", "name": "Reinforcement Learning", "score": 0.92},
        ]
    )

    out = await kg_r._link_entities_ann("Paradigm", "RL", fake_emb, fake_kg)
    assert len(out) == 1
    assert out[0].node_id == "el-42"
    assert out[0].label == "Paradigm"
    assert out[0].name == "Reinforcement Learning"
    assert out[0].confidence == 0.92

    # Confirm the Cypher call shape.
    cypher, params = fake_kg.query.await_args.args
    assert "db.index.vector.queryNodes" in cypher
    assert params["index_name"] == "paradigm_embedding_idx"
    assert params["k"] == 5
    assert params["vector"] == [0.1] * 1024


@pytest.mark.asyncio
async def test_ann_label_without_vector_index_returns_empty():
    """Labels without a vector index (e.g. Paper, Author, Equation,
    BrainRegion, Parameter) short-circuit to []."""
    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    fake_kg = MagicMock()
    fake_kg.query = AsyncMock()

    out = await kg_r._link_entities_ann("Paper", "Some Paper", fake_emb, fake_kg)
    assert out == []
    # No vector index → never embeds, never queries.
    fake_emb.embed_query.assert_not_awaited()
    fake_kg.query.assert_not_awaited()


@pytest.mark.asyncio
async def test_ann_label_with_index_but_no_name_prop_returns_empty():
    """Labels in `_VECTOR_INDEX_LABELS` (write side) but missing from
    `_LABEL_NAME_PROP` (read side) — Postulate, Formulation, Model —
    return [] cleanly instead of KeyError. Today these labels aren't
    surfaced through NER, but the read path must stay defensive."""
    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    fake_kg = MagicMock()
    fake_kg.query = AsyncMock()

    for label in ("Postulate", "Formulation", "Model"):
        out = await kg_r._link_entities_ann(label, "anything", fake_emb, fake_kg)
        assert out == [], f"{label} should short-circuit"
    fake_emb.embed_query.assert_not_awaited()
    fake_kg.query.assert_not_awaited()

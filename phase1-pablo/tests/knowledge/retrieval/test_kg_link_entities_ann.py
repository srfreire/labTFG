"""ANN-backed entity linking — replaces the O(N) Cypher table scan
with a single Qdrant ANN call against kg_entities_dense.

Ordering inside _link_entities:
    1. Exact case-insensitive match on the label's name property.
    2. ANN against kg_entities_dense (Task 4).
    3. (no fallback to table scan — that path is deleted).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.knowledge.retrieval import kg_retrieval as kg_r
from shared.vector_store import ScoredPoint


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
async def test_ann_below_threshold_returns_empty(monkeypatch):
    """If best ANN hit is below the similarity threshold, return [] —
    no fallback to table scan."""
    fake_vec = MagicMock()
    fake_vec.search_dense = AsyncMock(
        return_value=[
            ScoredPoint(
                id="Paradigm:foo",
                score=0.50,
                payload={"label": "Paradigm", "key_value": "foo", "name": "Foo"},
            )
        ]
    )
    monkeypatch.setattr(kg_r, "_get_vector_store", lambda: fake_vec)

    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    fake_kg = MagicMock()

    out = await kg_r._link_entities_ann("Paradigm", "FooQuery", fake_emb, fake_kg)
    assert out == []


@pytest.mark.asyncio
async def test_ann_above_threshold_resolves_element_id(monkeypatch):
    """Above-threshold ANN hit resolves elementId via indexed Cypher MATCH
    on the natural key — keeps the O(1) lookup but skips the O(N) scan."""
    fake_vec = MagicMock()
    fake_vec.search_dense = AsyncMock(
        return_value=[
            ScoredPoint(
                id="Paradigm:rl",
                score=0.92,
                payload={
                    "label": "Paradigm",
                    "key_value": "rl",
                    "name": "Reinforcement Learning",
                },
            )
        ]
    )
    monkeypatch.setattr(kg_r, "_get_vector_store", lambda: fake_vec)

    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    fake_kg = MagicMock()
    fake_kg.unique_key_for = MagicMock(return_value="slug")
    fake_kg.query = AsyncMock(
        return_value=[{"id": "el-42", "name": "Reinforcement Learning"}]
    )

    out = await kg_r._link_entities_ann("Paradigm", "RL", fake_emb, fake_kg)
    assert len(out) == 1
    assert out[0].node_id == "el-42"
    assert out[0].label == "Paradigm"
    assert out[0].confidence == 0.92


@pytest.mark.asyncio
async def test_ann_no_vector_store_returns_empty(monkeypatch):
    """If shared.vectors is not initialised (e.g. Qdrant down), return
    [] cleanly rather than crashing."""
    monkeypatch.setattr(kg_r, "_get_vector_store", lambda: None)

    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    fake_kg = MagicMock()

    out = await kg_r._link_entities_ann("Paradigm", "RL", fake_emb, fake_kg)
    assert out == []

"""kg_writer upserts into kg_entities_dense after writing slug-like
nodes — so the entity ANN index stays current with the graph.

Test seam: kg_writer reads the embedding/vector services via two helper
funcs that the test monkeypatches.
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
async def test_paradigm_write_triggers_ann_upsert(monkeypatch):
    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(return_value=[[0.1] * 1024])

    fake_vec = MagicMock()
    fake_vec.upsert_dense = AsyncMock()

    fake_kg = MagicMock()
    fake_kg.execute_write = AsyncMock(return_value={"was_created": True})
    fake_kg.unique_key_for = MagicMock(return_value="slug")

    monkeypatch.setattr(w, "_get_embedding_service", lambda: fake_emb)
    monkeypatch.setattr(w, "_get_vector_store", lambda: fake_vec)

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

    await w.populate_kg(extraction, fake_kg)

    fake_emb.embed_texts.assert_awaited_once()
    fake_vec.upsert_dense.assert_awaited_once()
    call = fake_vec.upsert_dense.await_args
    # Single-point API: upsert_dense(collection, id=..., vector=..., payload=...).
    assert call.args[0] == "kg_entities_dense"
    payload = call.kwargs["payload"]
    assert payload["label"] == "Paradigm"
    assert payload["key_value"] == "rl"


@pytest.mark.asyncio
async def test_non_slug_label_does_not_trigger_ann_upsert(monkeypatch):
    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(return_value=[[0.1] * 1024])

    fake_vec = MagicMock()
    fake_vec.upsert_dense = AsyncMock()

    fake_kg = MagicMock()
    fake_kg.execute_write = AsyncMock(return_value={"was_created": True})
    fake_kg.unique_key_for = MagicMock(return_value="doi")

    monkeypatch.setattr(w, "_get_embedding_service", lambda: fake_emb)
    monkeypatch.setattr(w, "_get_vector_store", lambda: fake_vec)

    extraction = _ext(
        [
            NodeSpec(
                label="Paper",
                properties={"doi": "10.1/x", "title": "X"},
                natural_key="doi",
            )
        ]
    )

    await w.populate_kg(extraction, fake_kg)
    fake_vec.upsert_dense.assert_not_awaited()


@pytest.mark.asyncio
async def test_ann_failure_does_not_break_write(monkeypatch):
    """If Qdrant is down, the KG write should still complete cleanly —
    ANN sync is best-effort."""
    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(side_effect=RuntimeError("voyage down"))

    fake_vec = MagicMock()

    fake_kg = MagicMock()
    fake_kg.execute_write = AsyncMock(return_value={"was_created": True})
    fake_kg.unique_key_for = MagicMock(return_value="slug")

    monkeypatch.setattr(w, "_get_embedding_service", lambda: fake_emb)
    monkeypatch.setattr(w, "_get_vector_store", lambda: fake_vec)

    extraction = _ext(
        [
            NodeSpec(
                label="Paradigm",
                properties={"slug": "rl", "name": "RL", "description": "."},
                natural_key="slug",
            )
        ]
    )

    result = await w.populate_kg(extraction, fake_kg)
    # Write succeeded; ANN failure logged but not surfaced as an error.
    assert result.nodes_created == 1

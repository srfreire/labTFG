"""P4-002: ``seed_canonical_paradigms`` writes ``n.embedding`` on each
seeded Paradigm node so retrieval's ``_link_entities_ann`` (Cypher
``db.index.vector.queryNodes`` against ``paradigm_embedding_idx``) can
find the umbrella paradigms immediately, without a separate backfill.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.knowledge.seed import seed_canonical_paradigms


@pytest.fixture
def fixture_path(tmp_path: Path) -> Path:
    payload = [
        {
            "slug": "rl",
            "name": "Reinforcement Learning",
            "definition": "RL paradigm definition.",
        },
        {
            "slug": "ddm",
            "name": "Drift Diffusion Model",
            "definition": "DDM paradigm definition.",
        },
    ]
    p = tmp_path / "canonical-paradigms.json"
    p.write_text(json.dumps(payload))
    return p


@pytest.mark.asyncio
async def test_seed_writes_n_embedding_on_paradigm_nodes(fixture_path: Path):
    """Each seeded Paradigm gets a `MATCH ... SET n.embedding = $vector`
    Cypher write so the native vector index can find it."""
    fake_kg = MagicMock()
    fake_kg.execute_write = AsyncMock(return_value={"was_created": True})
    fake_kg.query = AsyncMock(return_value=[])

    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(return_value=[[0.11] * 1024, [0.22] * 1024])

    fake_vec = MagicMock()
    fake_vec.upsert_dense = AsyncMock()
    fake_vec.upsert_sparse = AsyncMock()

    result = await seed_canonical_paradigms(
        fake_kg, fake_emb, fake_vec, fixture_path=fixture_path
    )

    assert result["vectors_indexed"] == 2

    # Two MATCH ... SET n.embedding = $vector calls — one per paradigm.
    assert fake_kg.query.await_count == 2
    cyphers = [c.args[0] for c in fake_kg.query.await_args_list]
    params = [c.args[1] for c in fake_kg.query.await_args_list]
    for cypher in cyphers:
        assert "MATCH (n:Paradigm" in cypher
        assert "SET n.embedding = $vector" in cypher
    slugs = {p["slug"] for p in params}
    assert slugs == {"rl", "ddm"}
    vectors = {tuple(p["vector"]) for p in params}
    assert tuple([0.11] * 1024) in vectors
    assert tuple([0.22] * 1024) in vectors


@pytest.mark.asyncio
async def test_seed_skips_embedding_when_no_vector_store(fixture_path: Path):
    """Without a vector store / embedding service, only the KG MERGE
    runs — no Qdrant writes, no `n.embedding` write."""
    fake_kg = MagicMock()
    fake_kg.execute_write = AsyncMock(return_value={"was_created": True})
    fake_kg.query = AsyncMock(return_value=[])

    result = await seed_canonical_paradigms(
        fake_kg, None, None, fixture_path=fixture_path
    )

    assert result["vectors_indexed"] == 0
    fake_kg.query.assert_not_awaited()

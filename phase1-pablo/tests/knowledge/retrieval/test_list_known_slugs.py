"""list_known_slugs returns (slug, definition) tuples directly from the
KG without going through markdown rendering."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.knowledge.retrieval.models import RetrievalResult


def _result(slug: str | None, score: float = 0.9) -> RetrievalResult:
    metadata = {"namespace": "paradigm"}
    if slug is not None:
        metadata["slug"] = slug
    return RetrievalResult(
        text="",
        score=score,
        source="dense",
        metadata=metadata,
    )


@pytest.mark.asyncio
async def test_list_known_slugs_returns_tuples():
    from decisionlab.knowledge.retrieval import tool as tool_mod

    fake_records = [
        {
            "slug": "reinforcement-learning",
            "name": "Reinforcement Learning",
            "description": "Value-based action selection.",
        },
        {
            "slug": "prospect-theory",
            "name": "Prospect Theory",
            "description": "Asymmetric value function over gains/losses.",
        },
    ]

    fake_kg = MagicMock()
    fake_kg.query = AsyncMock(return_value=fake_records)

    out = await tool_mod.list_known_slugs(
        query="how do animals decide which patch to forage",
        kg=fake_kg,
        vectors=None,
        embeddings=None,
        namespace="paradigm",
        top_k=5,
    )
    assert out == [
        ("reinforcement-learning", "Value-based action selection."),
        ("prospect-theory", "Asymmetric value function over gains/losses."),
    ]


@pytest.mark.asyncio
async def test_list_known_slugs_ranks_learned_kg_paradigms_from_neo4j_vector(
    monkeypatch,
):
    from decisionlab.knowledge.retrieval import tool as tool_mod

    fake_kg = MagicMock()
    fake_kg.query = AsyncMock(
        side_effect=[
            [
                {
                    "slug": "learned-foraging-theory",
                    "name": "Learned Foraging Theory",
                    "description": "Patch choice from prior runs.",
                    "score": 0.91,
                },
                {
                    "slug": "reinforcement-learning",
                    "name": "Reinforcement Learning",
                    "description": "Reward-based learning.",
                    "score": 0.82,
                },
            ],
            [
                {
                    "slug": "learned-foraging-theory",
                    "description": "Patch choice from prior runs.",
                },
                {
                    "slug": "reinforcement-learning",
                    "description": "Reward-based learning.",
                },
            ],
        ]
    )
    fake_embeddings = MagicMock()
    fake_embeddings.embed_query = AsyncMock(return_value=[0.1] * 1024)
    monkeypatch.setattr(
        tool_mod,
        "vector_retrieve",
        AsyncMock(return_value=([_result(None)], [])),
    )

    out = await tool_mod.list_known_slugs(
        query="learned patch foraging decisions",
        kg=fake_kg,
        vectors=MagicMock(),
        embeddings=fake_embeddings,
        namespace="paradigm",
        top_k=2,
    )

    assert out == [
        ("learned-foraging-theory", "Patch choice from prior runs."),
        ("reinforcement-learning", "Reward-based learning."),
    ]
    cypher, params = fake_kg.query.await_args_list[0].args
    assert "db.index.vector.queryNodes" in cypher
    assert params["index_name"] == "paradigm_embedding_idx"


@pytest.mark.asyncio
async def test_list_known_slugs_qdrant_partial_hits_still_top_up_from_kg(
    monkeypatch,
):
    from decisionlab.knowledge.retrieval import tool as tool_mod

    fake_kg = MagicMock()
    fake_kg.query = AsyncMock(
        side_effect=[
            [],
            [
                {
                    "slug": "learned-foraging-theory",
                    "name": "Learned Foraging Theory",
                    "description": "Learned KG-only paradigm.",
                },
                {
                    "slug": "prospect-theory",
                    "name": "Prospect Theory",
                    "description": "Utility over gains and losses.",
                },
            ],
            [
                {
                    "slug": "reinforcement-learning",
                    "description": "Seeded Qdrant/KG paradigm.",
                },
                {
                    "slug": "learned-foraging-theory",
                    "description": "Learned KG-only paradigm.",
                },
                {
                    "slug": "prospect-theory",
                    "description": "Utility over gains and losses.",
                },
            ],
        ]
    )
    fake_embeddings = MagicMock()
    fake_embeddings.embed_query = AsyncMock(return_value=[0.2] * 1024)
    monkeypatch.setattr(
        tool_mod,
        "vector_retrieve",
        AsyncMock(return_value=([_result("reinforcement-learning")], [])),
    )

    out = await tool_mod.list_known_slugs(
        query="learned foraging",
        kg=fake_kg,
        vectors=MagicMock(),
        embeddings=fake_embeddings,
        namespace="paradigm",
        top_k=3,
    )

    assert out == [
        ("reinforcement-learning", "Seeded Qdrant/KG paradigm."),
        ("learned-foraging-theory", "Learned KG-only paradigm."),
        ("prospect-theory", "Utility over gains and losses."),
    ]
    _cypher, params = fake_kg.query.await_args_list[1].args
    assert params["exclude"] == ["reinforcement-learning"]
    assert params["k"] == 2


@pytest.mark.asyncio
async def test_list_known_slugs_degrades_to_plain_kg_when_vector_query_fails():
    from decisionlab.knowledge.retrieval import tool as tool_mod

    fake_kg = MagicMock()
    fake_kg.query = AsyncMock(
        side_effect=[
            RuntimeError("vector index unavailable"),
            [
                {
                    "slug": "reinforcement-learning",
                    "name": "Reinforcement Learning",
                    "description": "Value-based action selection.",
                }
            ],
            [
                {
                    "slug": "reinforcement-learning",
                    "description": "Value-based action selection.",
                }
            ],
        ]
    )
    fake_embeddings = MagicMock()
    fake_embeddings.embed_query = AsyncMock(return_value=[0.3] * 1024)

    out = await tool_mod.list_known_slugs(
        query="reward learning",
        kg=fake_kg,
        vectors=None,
        embeddings=fake_embeddings,
        namespace="paradigm",
        top_k=2,
    )

    assert out == [("reinforcement-learning", "Value-based action selection.")]


@pytest.mark.asyncio
async def test_list_known_slugs_empty_when_kg_unavailable():
    from decisionlab.knowledge.retrieval import tool as tool_mod

    out = await tool_mod.list_known_slugs(
        query="probe",
        kg=None,
        vectors=None,
        embeddings=None,
        namespace="paradigm",
        top_k=5,
    )
    assert out == []


@pytest.mark.asyncio
async def test_list_known_slugs_rejects_non_paradigm_namespace():
    from decisionlab.knowledge.retrieval import tool as tool_mod

    with pytest.raises(ValueError, match="namespace"):
        await tool_mod.list_known_slugs(
            query="x",
            kg=MagicMock(),
            vectors=None,
            embeddings=None,
            namespace="formulation",
            top_k=5,
        )

"""list_known_slugs returns (slug, definition) tuples directly from the
KG without going through markdown rendering."""

from unittest.mock import AsyncMock, MagicMock

import pytest


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

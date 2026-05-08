"""list_known_slugs returns (slug, definition) tuples directly from the
KG without going through markdown rendering."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_list_known_slugs_returns_tuples(monkeypatch):
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
    fake_kg.execute_query = AsyncMock(return_value=fake_records)

    monkeypatch.setattr(tool_mod, "_get_kg", lambda: fake_kg)
    # Force the KG-only path (no vector ranking) so the test is hermetic.
    monkeypatch.setattr(tool_mod, "_get_vector_store", lambda: None)
    monkeypatch.setattr(tool_mod, "_get_embedding_service", lambda: None)

    out = await tool_mod.list_known_slugs(
        query="how do animals decide which patch to forage",
        namespace="paradigm",
        top_k=5,
    )
    assert out == [
        ("reinforcement-learning", "Value-based action selection."),
        ("prospect-theory", "Asymmetric value function over gains/losses."),
    ]


@pytest.mark.asyncio
async def test_list_known_slugs_empty_when_kg_unavailable(monkeypatch):
    from decisionlab.knowledge.retrieval import tool as tool_mod

    monkeypatch.setattr(tool_mod, "_get_kg", lambda: None)
    monkeypatch.setattr(tool_mod, "_get_vector_store", lambda: None)
    monkeypatch.setattr(tool_mod, "_get_embedding_service", lambda: None)
    out = await tool_mod.list_known_slugs(
        query="probe", namespace="paradigm", top_k=5
    )
    assert out == []


@pytest.mark.asyncio
async def test_list_known_slugs_rejects_non_paradigm_namespace(monkeypatch):
    from decisionlab.knowledge.retrieval import tool as tool_mod

    monkeypatch.setattr(tool_mod, "_get_kg", lambda: MagicMock())
    monkeypatch.setattr(tool_mod, "_get_vector_store", lambda: None)
    monkeypatch.setattr(tool_mod, "_get_embedding_service", lambda: None)
    with pytest.raises(ValueError, match="namespace"):
        await tool_mod.list_known_slugs(query="x", namespace="formulation", top_k=5)

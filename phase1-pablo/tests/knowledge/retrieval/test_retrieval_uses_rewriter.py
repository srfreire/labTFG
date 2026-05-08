"""Wire the query rewriter into vector retrieval and KG NER."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.knowledge.retrieval import (
    kg_retrieval as kg_r,
)
from decisionlab.knowledge.retrieval import (
    vector_retrieval as vr,
)
from decisionlab.knowledge.retrieval.query_rewriter import _QueryRewrite


@pytest.mark.asyncio
async def test_vector_retrieve_dense_uses_focal_concept(monkeypatch):
    """Dense embedding path should run on the focal_concept, not the
    raw multi-sentence query — a noisy long query degrades dense recall."""
    rewrite_mock = AsyncMock(
        return_value=_QueryRewrite(
            focal_concept="reinforcement learning",
            keywords=["q-learning", "exploration"],
        )
    )
    monkeypatch.setattr(vr, "_rewrite", rewrite_mock)

    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    fake_vs = MagicMock()
    fake_vs.search_dense = AsyncMock(return_value=[])
    fake_vs.search_sparse = AsyncMock(return_value=[])

    await vr.vector_retrieve(
        query="How does Q-learning trade off exploration and exploitation?",
        embedding_service=fake_emb,
        vector_store=fake_vs,
        limit=5,
        client=MagicMock(),
    )

    # Dense path embedded the focal concept.
    fake_emb.embed_query.assert_awaited_with("reinforcement learning")


@pytest.mark.asyncio
async def test_vector_retrieve_sparse_uses_query_plus_keywords(monkeypatch):
    """Sparse BM25 path should use the original query (so phrase matches
    survive) plus the extracted keywords (which boost lemma overlap)."""
    rewrite_mock = AsyncMock(
        return_value=_QueryRewrite(
            focal_concept="reinforcement learning",
            keywords=["q-learning", "exploration"],
        )
    )
    monkeypatch.setattr(vr, "_rewrite", rewrite_mock)

    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    fake_vs = MagicMock()
    fake_vs.search_dense = AsyncMock(return_value=[])
    fake_vs.search_sparse = AsyncMock(return_value=[])

    await vr.vector_retrieve(
        query="How does Q-learning trade off exploration?",
        embedding_service=fake_emb,
        vector_store=fake_vs,
        limit=5,
        client=MagicMock(),
    )

    # Sparse path got query + keywords concatenated.
    sparse_call = fake_vs.search_sparse.call_args
    text_used = sparse_call.args[1]
    assert "Q-learning" in text_used  # original query preserved
    assert "q-learning" in text_used  # keyword appended


@pytest.mark.asyncio
async def test_vector_retrieve_no_client_uses_raw_query(monkeypatch):
    """Backwards-compat: when no client is passed (existing call sites),
    behaviour matches the pre-rewriter baseline — both paths use the raw
    query and the rewriter is never invoked."""
    rewrite_mock = AsyncMock()
    monkeypatch.setattr(vr, "_rewrite", rewrite_mock)

    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    fake_vs = MagicMock()
    fake_vs.search_dense = AsyncMock(return_value=[])
    fake_vs.search_sparse = AsyncMock(return_value=[])

    await vr.vector_retrieve(
        query="raw question",
        embedding_service=fake_emb,
        vector_store=fake_vs,
        limit=5,
    )

    rewrite_mock.assert_not_called()
    fake_emb.embed_query.assert_awaited_with("raw question")


@pytest.mark.asyncio
async def test_kg_ner_receives_keyword_hints(monkeypatch):
    """When kg_retrieve has a rewriter result, the NER prompt should
    include a 'Hint keywords:' line so the model is biased toward the
    rewriter's terms."""
    rewrite_mock = AsyncMock(
        return_value=_QueryRewrite(
            focal_concept="reinforcement learning",
            keywords=["q-learning", "exploration"],
        )
    )
    monkeypatch.setattr(kg_r, "_rewrite", rewrite_mock)

    captured_messages: list[dict] = []

    async def fake_messages_create(**kwargs):
        captured_messages.append(kwargs["messages"][0])
        # Return a minimal valid NER response.
        block = MagicMock()
        block.type = "text"
        block.text = '{"entities": []}'
        resp = MagicMock()
        resp.content = [block]
        resp.stop_reason = "end_turn"
        resp.usage = None
        return resp

    fake_client = MagicMock()
    fake_client.messages.create = fake_messages_create

    fake_kg = MagicMock()
    fake_kg.query = AsyncMock(return_value=[])
    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    await kg_r.kg_retrieve(
        query="How does Q-learning trade off exploration?",
        kg=fake_kg,
        embedding_service=fake_emb,
        client=fake_client,
    )

    assert captured_messages, "NER call was not made"
    user_text = captured_messages[0]["content"]
    assert "Hint keywords" in user_text or "hint keywords" in user_text.lower()
    assert "q-learning" in user_text

"""Real-LLM tests for `shared.embedding.EmbeddingService`.

Hits the real Voyage AI API for embeddings and ZeroEntropy for reranking.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_real_embed_query_returns_1024_dim(real_embedding_service):
    """Voyage voyage-4-lite returns a 1024-dim vector for a query."""
    vec = await real_embedding_service.embed_query("dopamine reward prediction")
    assert len(vec) == 1024
    assert all(isinstance(v, float) for v in vec)


@pytest.mark.asyncio
async def test_real_embed_texts_handles_small_batch(real_embedding_service):
    """voyage-4-large produces 1024-dim vectors for each input."""
    texts = [
        "homeostatic regulation",
        "hedonic reward",
        "actor-critic reinforcement learning",
    ]
    vectors = await real_embedding_service.embed_texts(texts)
    assert len(vectors) == 3
    for v in vectors:
        assert len(v) == 1024


@pytest.mark.asyncio
async def test_real_rerank_orders_by_relevance(real_embedding_service):
    """ZeroEntropy zerank-2 puts the on-topic doc first."""
    docs = [
        "weather forecast for Madrid tomorrow",
        "Q-learning convergence guarantees in reinforcement learning",
        "paella recipe with seafood",
    ]
    results = await real_embedding_service.rerank(
        "Q-learning convergence", docs, top_k=3
    )
    assert len(results) == 3
    # Top result should be the on-topic Q-learning doc
    assert "Q-learning" in results[0].document
    # Scores monotonically non-increasing
    for i in range(len(results) - 1):
        assert results[i].score >= results[i + 1].score

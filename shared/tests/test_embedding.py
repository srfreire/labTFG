"""Integration tests for EmbeddingService (requires VOYAGE_API_KEY)."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

from shared.embedding import EmbeddingService

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def svc():
    """Yield an EmbeddingService; skip if API keys missing."""
    voyage_key = os.environ.get("VOYAGE_API_KEY")
    ze_key = os.environ.get("ZEROENTROPY_API_KEY")
    if not voyage_key:
        pytest.skip("VOYAGE_API_KEY not set")
    if not ze_key:
        pytest.skip("ZEROENTROPY_API_KEY not set")
    return EmbeddingService(voyage_key, ze_key)


# -- AC1: single text embedding -----------------------------------------------


@pytest.mark.asyncio
async def test_embed_single_text(svc: EmbeddingService):
    """embed_texts(['hello world']) returns one vector of length 1024."""
    result = await svc.embed_texts(["hello world"])
    assert len(result) == 1
    assert len(result[0]) == 1024
    assert all(isinstance(v, float) for v in result[0])


# -- AC2: auto-batching -------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_auto_batches(svc: EmbeddingService):
    """embed_texts with 200 texts auto-batches and returns 200 vectors."""
    texts = [f"test text number {i}" for i in range(200)]
    result = await svc.embed_texts(texts)
    assert len(result) == 200
    assert all(len(v) == 1024 for v in result)


# -- AC3: embed_query ---------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_query(svc: EmbeddingService):
    """embed_query returns a single vector of length 1024."""
    result = await svc.embed_query("test")
    assert len(result) == 1024
    assert all(isinstance(v, float) for v in result)


# -- AC4: rerank ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank(svc: EmbeddingService):
    """rerank returns ordered results with Q-learning doc scoring highest."""
    docs = [
        "Q-learning convergence",
        "weather forecast",
        "reinforcement learning",
    ]
    result = await svc.rerank("Q-learning", docs)
    assert len(result) == 3
    assert result[0].document == "Q-learning convergence"
    assert all(r.score >= result[i + 1].score for i, r in enumerate(result[:-1]))


# -- AC5: empty embed ---------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_empty(svc: EmbeddingService):
    """embed_texts([]) returns [] without API call."""
    result = await svc.embed_texts([])
    assert result == []


# -- AC6: empty rerank --------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_empty(svc: EmbeddingService):
    """rerank with empty documents returns []."""
    result = await svc.rerank("query", [])
    assert result == []

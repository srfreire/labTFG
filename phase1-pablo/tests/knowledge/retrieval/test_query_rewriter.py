"""query_rewriter — Haiku-backed focal_concept + keywords extractor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.knowledge.retrieval import query_rewriter as qr


@pytest.fixture(autouse=True)
def _clear_cache():
    qr._cache.clear()
    yield
    qr._cache.clear()


@pytest.mark.asyncio
async def test_rewrite_returns_focal_and_keywords(monkeypatch):
    async def fake_call_structured(**kwargs):
        return qr._QueryRewrite(
            focal_concept="reinforcement learning",
            keywords=["q-learning", "exploration", "exploitation"],
        )

    monkeypatch.setattr(qr, "call_structured", fake_call_structured)

    out = await qr.rewrite(
        "How does Q-learning trade off exploration and exploitation?",
        client=MagicMock(),
    )
    assert out.focal_concept == "reinforcement learning"
    assert "q-learning" in out.keywords


@pytest.mark.asyncio
async def test_rewrite_caches_by_query_hash(monkeypatch):
    calls = 0

    async def fake_call_structured(**kwargs):
        nonlocal calls
        calls += 1
        return qr._QueryRewrite(focal_concept="x", keywords=[])

    monkeypatch.setattr(qr, "call_structured", fake_call_structured)

    await qr.rewrite("q", client=MagicMock())
    await qr.rewrite("q", client=MagicMock())
    assert calls == 1


@pytest.mark.asyncio
async def test_rewrite_failure_falls_back_to_passthrough(monkeypatch):
    """If the LLM call raises, return focal=query, keywords=[] so
    callers can always proceed."""

    async def boom(**_):
        raise RuntimeError("haiku timeout")

    monkeypatch.setattr(qr, "call_structured", boom)

    out = await qr.rewrite("a long question text", client=MagicMock())
    assert out.focal_concept == "a long question text"
    assert out.keywords == []


@pytest.mark.asyncio
async def test_rewrite_passthrough_is_also_cached(monkeypatch):
    """A failure result is cached so repeated calls don't re-hit a
    flapping endpoint within the same process."""
    calls = 0

    async def boom(**_):
        nonlocal calls
        calls += 1
        raise RuntimeError("voyage down")

    monkeypatch.setattr(qr, "call_structured", boom)

    await qr.rewrite("q", client=MagicMock())
    await qr.rewrite("q", client=MagicMock())
    assert calls == 1

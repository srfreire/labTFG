"""Unit tests for the Corrective RAG evaluator with web search fallback.

All external services (Anthropic Haiku, DuckDuckGo, Semantic Scholar, Voyage AI)
are mocked — no live infrastructure required.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.embedding import RankedResult

from decisionlab.domain.models import SearchResult
from decisionlab.knowledge.retrieval.models import CRAGResult, RetrievalResult


# -- helpers -------------------------------------------------------------------


def _rr(
    text: str,
    score: float = 0.5,
    source: str = "fused",
    metadata: dict | None = None,
) -> RetrievalResult:
    return RetrievalResult(text=text, score=score, source=source, metadata=metadata or {})


def _haiku_response(evaluations: list[dict]) -> AsyncMock:
    """Build a mock AsyncAnthropic whose messages.create returns evaluations JSON."""
    client = AsyncMock()
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = json.dumps({"evaluations": evaluations})
    response = MagicMock()
    response.content = [content_block]
    client.messages.create = AsyncMock(return_value=response)
    return client


def _mock_emb(ranked: list[RankedResult] | None = None, vector: list[float] | None = None) -> AsyncMock:
    """Build a mock EmbeddingService with preset rerank and embed_query."""
    emb = AsyncMock()
    emb.rerank = AsyncMock(return_value=ranked or [])
    emb.embed_query = AsyncMock(return_value=vector or [0.1] * 1024)
    emb.embed_texts = AsyncMock(return_value=[vector or [0.1] * 1024])
    return emb


def _mock_search(results: list[SearchResult] | None = None) -> AsyncMock:
    """Build a mock WebSearchPort."""
    adapter = AsyncMock()
    adapter.search = AsyncMock(return_value=results or [])
    return adapter


# ==============================================================================
# AC1: CORRECT classification for relevant result
# ==============================================================================


class TestAC1_CorrectClassification:
    """A result about ghrelin when task is homeostatic regulation → CORRECT."""

    @pytest.mark.asyncio
    async def test_relevant_result_classified_correct(self):
        from decisionlab.knowledge.retrieval.crag import evaluate_results

        results = [_rr("Ghrelin modulates hunger via hypothalamic circuits")]
        client = _haiku_response([
            {"index": 0, "classification": "CORRECT", "reasoning": "Directly relevant"},
        ])

        crag = await evaluate_results(
            query="ghrelin hunger signaling",
            task_context="formalize homeostatic regulation",
            results=results,
            client=client,
        )

        assert isinstance(crag, CRAGResult)
        assert crag.evaluations[0]["classification"] == "CORRECT"


# ==============================================================================
# AC2: INCORRECT classification for domain mismatch
# ==============================================================================


class TestAC2_IncorrectClassification:
    """A result about ghrelin when task is stock trading Q-learning → INCORRECT."""

    @pytest.mark.asyncio
    async def test_domain_mismatch_classified_incorrect(self):
        from decisionlab.knowledge.retrieval.crag import evaluate_results

        results = [_rr("Ghrelin modulates hunger via hypothalamic circuits")]
        client = _haiku_response([
            {"index": 0, "classification": "INCORRECT", "reasoning": "Domain mismatch"},
        ])

        crag = await evaluate_results(
            query="ghrelin hunger signaling",
            task_context="build a Q-learning grid agent for stock trading",
            results=results,
            client=client,
        )

        assert crag.evaluations[0]["classification"] == "INCORRECT"


# ==============================================================================
# AC3: AMBIGUOUS classification for partial relevance
# ==============================================================================


class TestAC3_AmbiguousClassification:
    @pytest.mark.asyncio
    async def test_partial_relevance_classified_ambiguous(self):
        from decisionlab.knowledge.retrieval.crag import evaluate_results

        results = [_rr("Reward-based paradigm using dopamine pathways")]
        client = _haiku_response([
            {"index": 0, "classification": "AMBIGUOUS", "reasoning": "Same paradigm, different aspect"},
        ])

        crag = await evaluate_results(
            query="reward learning formulation",
            task_context="formalize incentive salience",
            results=results,
            client=client,
        )

        assert crag.evaluations[0]["classification"] == "AMBIGUOUS"


# ==============================================================================
# AC4: All INCORRECT → web_fallback action
# ==============================================================================


class TestAC4_WebFallback:
    """When all results INCORRECT, action=web_fallback and web_results_used > 0."""

    @pytest.mark.asyncio
    async def test_all_incorrect_triggers_web_fallback(self):
        from decisionlab.knowledge.retrieval.crag import evaluate_results

        results = [
            _rr("irrelevant doc 1"),
            _rr("irrelevant doc 2"),
        ]
        client = _haiku_response([
            {"index": 0, "classification": "INCORRECT", "reasoning": "Not useful"},
            {"index": 1, "classification": "INCORRECT", "reasoning": "Not useful"},
        ])

        search = _mock_search([
            SearchResult(title="Web result", url="https://example.com", snippet="Fresh web content"),
        ])
        emb = _mock_emb(ranked=[
            RankedResult(index=0, score=0.85, document="Fresh web content"),
        ])

        crag = await evaluate_results(
            query="Q-learning convergence",
            task_context="build RL agent",
            results=results,
            client=client,
            search_adapter=search,
            embedding_service=emb,
        )

        assert crag.action == "web_fallback"
        assert crag.web_results_used > 0
        assert len(crag.results) > 0


# ==============================================================================
# AC5: AMBIGUOUS → supplemented action with stored + web results
# ==============================================================================


class TestAC5_Supplemented:
    """When some AMBIGUOUS, action=supplemented with both stored and web results."""

    @pytest.mark.asyncio
    async def test_ambiguous_triggers_supplemented(self):
        from decisionlab.knowledge.retrieval.crag import evaluate_results

        results = [
            _rr("correct doc", score=0.9),
            _rr("ambiguous doc", score=0.7),
            _rr("incorrect doc", score=0.5),
        ]
        client = _haiku_response([
            {"index": 0, "classification": "CORRECT", "reasoning": "Good"},
            {"index": 1, "classification": "AMBIGUOUS", "reasoning": "Partial"},
            {"index": 2, "classification": "INCORRECT", "reasoning": "Bad"},
        ])

        search = _mock_search([
            SearchResult(title="Supplement", url="https://example.com", snippet="Supplementary web content"),
        ])
        emb = _mock_emb(ranked=[
            RankedResult(index=0, score=0.9, document="correct doc"),
            RankedResult(index=1, score=0.8, document="Supplementary web content"),
            RankedResult(index=2, score=0.6, document="ambiguous doc"),
        ])

        crag = await evaluate_results(
            query="reward paradigm",
            task_context="formalize reward learning",
            results=results,
            client=client,
            search_adapter=search,
            embedding_service=emb,
        )

        assert crag.action == "supplemented"
        assert crag.web_results_used > 0
        # Contains both stored and web results
        sources = {r.source for r in crag.results}
        assert len(crag.results) >= 2


# ==============================================================================
# AC6: All CORRECT → pass_through, no web search
# ==============================================================================


class TestAC6_PassThrough:
    """When all CORRECT, action=pass_through and no web search triggered."""

    @pytest.mark.asyncio
    async def test_all_correct_pass_through(self):
        from decisionlab.knowledge.retrieval.crag import evaluate_results

        results = [
            _rr("good doc 1"),
            _rr("good doc 2"),
        ]
        client = _haiku_response([
            {"index": 0, "classification": "CORRECT", "reasoning": "Relevant"},
            {"index": 1, "classification": "CORRECT", "reasoning": "Relevant"},
        ])

        search = _mock_search()

        crag = await evaluate_results(
            query="homeostatic regulation",
            task_context="formalize homeostatic paradigm",
            results=results,
            client=client,
            search_adapter=search,
        )

        assert crag.action == "pass_through"
        assert crag.web_results_used == 0
        assert len(crag.results) == 2
        # Web search was NOT called
        search.search.assert_not_awaited()


# ==============================================================================
# AC7: Web fallback uses DuckDuckGo adapter
# ==============================================================================


class TestAC7_UsesDuckDuckGo:
    """Web fallback calls the existing WebSearchPort adapter."""

    @pytest.mark.asyncio
    async def test_web_fallback_calls_search_adapter(self):
        from decisionlab.knowledge.retrieval.crag import web_fallback

        search = _mock_search([
            SearchResult(title="DDG Result", url="https://example.com", snippet="DDG snippet content"),
        ])
        emb = _mock_emb(ranked=[
            RankedResult(index=0, score=0.8, document="DDG snippet content"),
        ])

        results = await web_fallback(
            query="Q-learning convergence",
            search_adapter=search,
            embedding_service=emb,
            top_k=5,
        )

        search.search.assert_awaited_once()
        assert len(results) >= 1
        assert all(r.source == "web" for r in results)


# ==============================================================================
# AC8: Haiku failure → fail-open, default all to CORRECT
# ==============================================================================


class TestAC8_FailOpen:
    """If Haiku evaluation fails, all results default to CORRECT."""

    @pytest.mark.asyncio
    async def test_haiku_failure_defaults_to_correct(self):
        from decisionlab.knowledge.retrieval.crag import evaluate_results

        results = [_rr("some doc"), _rr("another doc")]

        # Haiku raises an exception
        client = AsyncMock()
        client.messages.create = AsyncMock(side_effect=RuntimeError("API down"))

        crag = await evaluate_results(
            query="test",
            task_context="test",
            results=results,
            client=client,
        )

        assert crag.action == "pass_through"
        assert len(crag.results) == 2
        assert all(e["classification"] == "CORRECT" for e in crag.evaluations)

    @pytest.mark.asyncio
    async def test_haiku_bad_json_defaults_to_correct(self):
        from decisionlab.knowledge.retrieval.crag import evaluate_results

        results = [_rr("some doc")]

        # Haiku returns garbage
        client = AsyncMock()
        content_block = MagicMock()
        content_block.type = "text"
        content_block.text = "Not valid JSON at all"
        response = MagicMock()
        response.content = [content_block]
        client.messages.create = AsyncMock(return_value=response)

        crag = await evaluate_results(
            query="test",
            task_context="test",
            results=results,
            client=client,
        )

        assert crag.action == "pass_through"
        assert len(crag.results) == 1
        assert crag.evaluations[0]["classification"] == "CORRECT"


# ==============================================================================
# Edge cases
# ==============================================================================


class TestEmptyInputs:
    """Empty results produce empty output."""

    @pytest.mark.asyncio
    async def test_empty_results_pass_through(self):
        from decisionlab.knowledge.retrieval.crag import evaluate_results

        client = AsyncMock()
        crag = await evaluate_results(
            query="test",
            task_context="test",
            results=[],
            client=client,
        )

        assert crag.action == "pass_through"
        assert crag.results == []
        assert crag.web_results_used == 0
        client.messages.create.assert_not_awaited()


class TestMixedCorrectIncorrect:
    """CORRECT + INCORRECT with no AMBIGUOUS → pass_through with only CORRECT."""

    @pytest.mark.asyncio
    async def test_correct_plus_incorrect_is_pass_through(self):
        from decisionlab.knowledge.retrieval.crag import evaluate_results

        results = [
            _rr("good doc"),
            _rr("bad doc"),
        ]
        client = _haiku_response([
            {"index": 0, "classification": "CORRECT", "reasoning": "Good"},
            {"index": 1, "classification": "INCORRECT", "reasoning": "Bad"},
        ])

        crag = await evaluate_results(
            query="test",
            task_context="test",
            results=results,
            client=client,
        )

        assert crag.action == "pass_through"
        assert len(crag.results) == 1
        assert crag.results[0].text == "good doc"
        assert crag.web_results_used == 0


class TestOOBHaikuIndex:
    """Out-of-bounds Haiku index is ignored; missing indices default to CORRECT."""

    @pytest.mark.asyncio
    async def test_oob_index_ignored(self):
        from decisionlab.knowledge.retrieval.crag import evaluate_results

        results = [_rr("only doc")]
        client = _haiku_response([
            {"index": 99, "classification": "INCORRECT", "reasoning": "Ghost"},
        ])

        crag = await evaluate_results(
            query="test",
            task_context="test",
            results=results,
            client=client,
        )

        # OOB index rejected → missing index 0 defaults to CORRECT → pass_through
        assert crag.action == "pass_through"
        assert len(crag.results) == 1


class TestWebFallbackEmpty:
    """Web fallback with no search results returns empty list."""

    @pytest.mark.asyncio
    async def test_web_fallback_no_results(self):
        from decisionlab.knowledge.retrieval.crag import web_fallback

        search = _mock_search([])
        emb = _mock_emb()

        results = await web_fallback("test", search, emb)

        assert results == []

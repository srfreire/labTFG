"""Unit tests for RRF fusion and Voyage AI reranking pipeline.

All external services (Voyage AI via EmbeddingService) are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from decisionlab.knowledge.retrieval.models import RetrievalResult
from shared.embedding import RankedResult

# -- helpers -------------------------------------------------------------------


def _rr(
    text: str,
    score: float = 0.5,
    source: str = "kg",
    metadata: dict | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        text=text, score=score, source=source, metadata=metadata or {}
    )


def _mock_emb(ranked: list[RankedResult] | None = None) -> AsyncMock:
    """Build a mock EmbeddingService with a preset rerank response."""
    emb = AsyncMock()
    emb.rerank = AsyncMock(return_value=ranked or [])
    return emb


# ==============================================================================
# AC1: RRF fusion score correctness
# ==============================================================================


class TestAC1_RRFScoreCorrectness:
    """A document in all 3 lists at rank 1 scores 3/(k+1)."""

    def test_document_in_all_three_lists_rank1(self):
        from decisionlab.knowledge.retrieval.fusion import rrf_fuse

        # Same text in all 3 channels, each at rank 1
        kg = [_rr("shared doc", source="kg")]
        dense = [_rr("shared doc", source="dense")]
        sparse = [_rr("shared doc", source="sparse")]

        results = rrf_fuse([kg, dense, sparse], k=60, top_n=10)

        assert len(results) == 1
        expected_score = 3.0 / (60 + 1)  # 3/(k+1) ≈ 0.04918
        assert abs(results[0].score - expected_score) < 1e-9

    def test_single_channel_rank1_score(self):
        from decisionlab.knowledge.retrieval.fusion import rrf_fuse

        kg = [_rr("only in kg", source="kg")]

        results = rrf_fuse([kg], k=60, top_n=10)

        assert len(results) == 1
        expected_score = 1.0 / (60 + 1)  # 1/(k+1)
        assert abs(results[0].score - expected_score) < 1e-9


# ==============================================================================
# AC2: RRF deduplication merges same passage with source tracking
# ==============================================================================


class TestAC2_Deduplication:
    """Same passage from dense and sparse merges into one entry with sources."""

    def test_dedup_merges_sources(self):
        from decisionlab.knowledge.retrieval.fusion import rrf_fuse

        dense = [_rr("reward learning passage", source="dense")]
        sparse = [_rr("reward learning passage", source="sparse")]

        results = rrf_fuse([dense, sparse], k=60, top_n=10)

        assert len(results) == 1
        assert set(results[0].metadata["sources"]) == {"dense", "sparse"}

    def test_dedup_whitespace_normalization(self):
        from decisionlab.knowledge.retrieval.fusion import rrf_fuse

        # Extra whitespace should still match
        dense = [_rr("reward  learning   passage", source="dense")]
        sparse = [_rr("reward learning passage", source="sparse")]

        results = rrf_fuse([dense, sparse], k=60, top_n=10)

        assert len(results) == 1

    def test_dedup_first_200_chars(self):
        from decisionlab.knowledge.retrieval.fusion import rrf_fuse

        base = "A" * 200
        # Same first 200 chars, different after
        dense = [_rr(base + " DIFFERENT DENSE ENDING", source="dense")]
        sparse = [_rr(base + " DIFFERENT SPARSE ENDING", source="sparse")]

        results = rrf_fuse([dense, sparse], k=60, top_n=10)

        # Should merge — first 200 chars match after normalization
        assert len(results) == 1

    def test_dedup_different_first_200_chars(self):
        from decisionlab.knowledge.retrieval.fusion import rrf_fuse

        dense = [_rr("A" * 200 + " suffix", source="dense")]
        sparse = [_rr("B" * 200 + " suffix", source="sparse")]

        results = rrf_fuse([dense, sparse], k=60, top_n=10)

        # Should NOT merge — first 200 chars differ
        assert len(results) == 2


# ==============================================================================
# AC3: Multi-channel presence beats single-channel high rank
# ==============================================================================


class TestAC3_MultiChannelWins:
    """Doc at rank 5 in all 3 channels beats doc at rank 1 in one channel."""

    def test_multi_channel_scores_higher(self):
        from decisionlab.knowledge.retrieval.fusion import rrf_fuse

        # Doc A: rank 1 in kg only
        # Doc B: rank 5 in all 3 channels
        kg = [
            _rr("doc A", source="kg"),
            _rr("filler2", source="kg"),
            _rr("filler3", source="kg"),
            _rr("filler4", source="kg"),
            _rr("doc B", source="kg"),
        ]
        dense = [
            _rr("filler5", source="dense"),
            _rr("filler6", source="dense"),
            _rr("filler7", source="dense"),
            _rr("filler8", source="dense"),
            _rr("doc B", source="dense"),
        ]
        sparse = [
            _rr("filler9", source="sparse"),
            _rr("filler10", source="sparse"),
            _rr("filler11", source="sparse"),
            _rr("filler12", source="sparse"),
            _rr("doc B", source="sparse"),
        ]

        results = rrf_fuse([kg, dense, sparse], k=60, top_n=30)

        doc_a = next(r for r in results if "doc A" in r.text)
        doc_b = next(r for r in results if "doc B" in r.text)

        # Doc A: 1/(60+1) ≈ 0.0164
        # Doc B: 3/(60+5) ≈ 0.0462
        assert doc_b.score > doc_a.score


# ==============================================================================
# AC4: Reranking reorders results
# ==============================================================================


class TestAC4_RerankingReorders:
    """A semantically relevant doc with low RRF score can move up after reranking."""

    @pytest.mark.asyncio
    async def test_reranking_reorders_by_relevance(self):
        from decisionlab.knowledge.retrieval.fusion import rerank_results

        # Input: 3 results ordered by RRF score
        results = [
            _rr("high rrf but irrelevant", score=0.05, source="kg"),
            _rr("medium rrf", score=0.03, source="dense"),
            _rr("low rrf but very relevant", score=0.01, source="sparse"),
        ]

        # Reranker says the 3rd doc (index 2) is most relevant
        emb = _mock_emb(
            ranked=[
                RankedResult(index=2, score=0.95, document="low rrf but very relevant"),
                RankedResult(index=0, score=0.7, document="high rrf but irrelevant"),
                RankedResult(index=1, score=0.5, document="medium rrf"),
            ]
        )

        reranked = await rerank_results(
            "test query", results, emb, top_k=3, threshold=0.0
        )

        # After reranking, "low rrf but very relevant" should be first
        assert reranked[0].text == "low rrf but very relevant"
        assert reranked[0].score == 0.95

    @pytest.mark.asyncio
    async def test_reranking_preserves_metadata(self):
        from decisionlab.knowledge.retrieval.fusion import rerank_results

        results = [
            _rr(
                "doc",
                score=0.05,
                source="kg",
                metadata={"node_id": "n1", "run_id": "r1"},
            ),
        ]
        emb = _mock_emb(
            ranked=[
                RankedResult(index=0, score=0.8, document="doc"),
            ]
        )

        reranked = await rerank_results("q", results, emb, top_k=1, threshold=0.0)

        assert reranked[0].metadata["node_id"] == "n1"
        assert reranked[0].metadata["reranker_score"] == 0.8
        assert reranked[0].metadata["pre_rerank_score"] == 0.05


# ==============================================================================
# AC5: Threshold filtering
# ==============================================================================


class TestAC5_ThresholdFiltering:
    """Results with reranker score < threshold are removed."""

    @pytest.mark.asyncio
    async def test_below_threshold_removed(self):
        from decisionlab.knowledge.retrieval.fusion import rerank_results

        results = [
            _rr("relevant", score=0.05),
            _rr("marginal", score=0.04),
            _rr("irrelevant", score=0.03),
        ]
        emb = _mock_emb(
            ranked=[
                RankedResult(index=0, score=0.8, document="relevant"),
                RankedResult(index=1, score=0.25, document="marginal"),  # below 0.3
                RankedResult(index=2, score=0.1, document="irrelevant"),  # below 0.3
            ]
        )

        reranked = await rerank_results("q", results, emb, top_k=3, threshold=0.3)

        assert len(reranked) == 1
        assert reranked[0].text == "relevant"

    @pytest.mark.asyncio
    async def test_all_below_threshold_returns_empty(self):
        from decisionlab.knowledge.retrieval.fusion import rerank_results

        results = [_rr("bad", score=0.01)]
        emb = _mock_emb(
            ranked=[
                RankedResult(index=0, score=0.1, document="bad"),
            ]
        )

        reranked = await rerank_results("q", results, emb, top_k=1, threshold=0.3)

        assert reranked == []


# ==============================================================================
# AC6: Empty input lists
# ==============================================================================


class TestAC6_EmptyInputs:
    """Empty input lists produce empty output without errors."""

    def test_rrf_empty_lists(self):
        from decisionlab.knowledge.retrieval.fusion import rrf_fuse

        results = rrf_fuse([], k=60, top_n=30)
        assert results == []

    def test_rrf_all_empty_channels(self):
        from decisionlab.knowledge.retrieval.fusion import rrf_fuse

        results = rrf_fuse([[], [], []], k=60, top_n=30)
        assert results == []

    @pytest.mark.asyncio
    async def test_rerank_empty_results(self):
        from decisionlab.knowledge.retrieval.fusion import rerank_results

        emb = _mock_emb()
        reranked = await rerank_results("q", [], emb)
        assert reranked == []
        emb.rerank.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fuse_and_rerank_all_empty(self):
        from decisionlab.knowledge.retrieval.fusion import fuse_and_rerank

        emb = _mock_emb()
        results = await fuse_and_rerank("q", [], [], [], emb)
        assert results == []


# ==============================================================================
# AC7: fuse_and_rerank end-to-end
# ==============================================================================


class TestAC7_FuseAndRerankE2E:
    """3 channels with 20 results each → RRF top-30 → rerank top-10 → <=10 results."""

    @pytest.mark.asyncio
    async def test_e2e_pipeline(self):
        from decisionlab.knowledge.retrieval.fusion import fuse_and_rerank

        # 20 results per channel, some overlap
        kg = [_rr(f"kg doc {i}", source="kg") for i in range(20)]
        dense = [_rr(f"dense doc {i}", source="dense") for i in range(20)]
        sparse = [_rr(f"sparse doc {i}", source="sparse") for i in range(20)]

        # Mock reranker returns top 10 with scores above threshold
        rerank_response = [
            RankedResult(index=i, score=0.9 - i * 0.05, document=f"doc {i}")
            for i in range(10)
        ]
        emb = _mock_emb(ranked=rerank_response)

        results = await fuse_and_rerank(
            "test query",
            kg,
            dense,
            sparse,
            emb,
            rrf_top_n=30,
            rerank_top_k=10,
            rerank_threshold=0.3,
        )

        # Should have at most 10 results
        assert len(results) <= 10
        # All scores above threshold
        assert all(r.score >= 0.3 for r in results)

    @pytest.mark.asyncio
    async def test_e2e_calls_rerank_with_rrf_output(self):
        from decisionlab.knowledge.retrieval.fusion import fuse_and_rerank

        kg = [_rr("only doc", source="kg")]
        emb = _mock_emb(
            ranked=[
                RankedResult(index=0, score=0.85, document="only doc"),
            ]
        )

        await fuse_and_rerank("q", kg, [], [], emb)

        # rerank was called with the RRF output texts
        emb.rerank.assert_awaited_once()
        call_args = emb.rerank.call_args
        assert call_args[1]["query"] == "q" or call_args[0][0] == "q"


# ==============================================================================
# Additional edge cases
# ==============================================================================


class TestRerankOOBGuard:
    """Out-of-bounds reranker index is skipped gracefully."""

    @pytest.mark.asyncio
    async def test_oob_index_skipped(self):
        from decisionlab.knowledge.retrieval.fusion import rerank_results

        results = [_rr("only doc", score=0.05)]
        emb = _mock_emb(
            ranked=[
                RankedResult(index=0, score=0.9, document="only doc"),
                RankedResult(index=99, score=0.8, document="ghost"),  # OOB
            ]
        )

        reranked = await rerank_results("q", results, emb, top_k=2, threshold=0.0)

        assert len(reranked) == 1
        assert reranked[0].text == "only doc"


class TestDedupMetadataMerge:
    """Metadata from all channels is merged during deduplication."""

    def test_metadata_from_multiple_channels_merged(self):
        from decisionlab.knowledge.retrieval.fusion import rrf_fuse

        kg = [_rr("shared doc", source="kg", metadata={"node_id": "n1"})]
        dense = [_rr("shared doc", source="dense", metadata={"embedding_id": "e99"})]

        results = rrf_fuse([kg, dense], k=60, top_n=10)

        assert len(results) == 1
        # Both metadata keys present
        assert results[0].metadata["node_id"] == "n1"
        assert results[0].metadata["embedding_id"] == "e99"


class TestRRFSorting:
    """RRF results are sorted by score descending."""

    def test_output_sorted_descending(self):
        from decisionlab.knowledge.retrieval.fusion import rrf_fuse

        kg = [_rr("low rank", source="kg")]
        dense = [
            _rr("high rank", source="dense"),
            _rr("low rank", source="dense"),  # overlap with kg
        ]

        results = rrf_fuse([kg, dense], k=60, top_n=10)

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_top_n_limits_output(self):
        from decisionlab.knowledge.retrieval.fusion import rrf_fuse

        kg = [_rr(f"doc {i}", source="kg") for i in range(50)]

        results = rrf_fuse([kg], k=60, top_n=5)

        assert len(results) == 5

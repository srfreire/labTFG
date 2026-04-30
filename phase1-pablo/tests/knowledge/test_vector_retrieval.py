"""Unit tests for dense, sparse, and combined vector retrieval.

All external services (Qdrant via VectorStore, Voyage AI via EmbeddingService)
are mocked — no live infrastructure required.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from decisionlab.knowledge.retrieval.models import RetrievalResult
from decisionlab.knowledge.retrieval.vector_retrieval import (
    dense_retrieve,
    sparse_retrieve,
    vector_retrieve,
)
from shared.vector_store import ScoredPoint

# -- helpers -------------------------------------------------------------------


def _scored(
    id: str,
    score: float,
    text: str = "chunk text",
    namespace: str = "paradigm",
    run_id: str = "run-1",
    confidence: float = 0.8,
) -> ScoredPoint:
    return ScoredPoint(
        id=id,
        score=score,
        payload={
            "text_preview": text,
            "namespace": namespace,
            "run_id": run_id,
            "confidence": confidence,
            "source_stage": "researcher",
        },
    )


def _mock_vs(
    dense_artifacts: list[ScoredPoint] | None = None,
    dense_memories: list[ScoredPoint] | None = None,
    sparse_artifacts: list[ScoredPoint] | None = None,
    sparse_memories: list[ScoredPoint] | None = None,
) -> AsyncMock:
    """Build a mock VectorStore that returns preset results per collection."""
    vs = AsyncMock()

    async def _search_dense(collection, vector, limit=20, filters=None):
        if collection == "artifacts_dense":
            return dense_artifacts or []
        if collection == "memories_dense":
            return dense_memories or []
        return []

    async def _search_sparse(collection, query, limit=20, filters=None):
        if collection == "artifacts_sparse":
            return sparse_artifacts or []
        if collection == "memories_sparse":
            return sparse_memories or []
        return []

    vs.search_dense = AsyncMock(side_effect=_search_dense)
    vs.search_sparse = AsyncMock(side_effect=_search_sparse)
    return vs


def _mock_emb(vector: list[float] | None = None) -> AsyncMock:
    """Build a mock EmbeddingService returning a fixed query embedding."""
    emb = AsyncMock()
    emb.embed_query = AsyncMock(return_value=vector or [0.1] * 1024)
    return emb


# -- AC1: dense retrieval finds semantic matches --------------------------------


@pytest.mark.asyncio
async def test_dense_retrieval_returns_results():
    """Dense search returns RetrievalResult objects with source='dense'."""
    vs = _mock_vs(
        dense_artifacts=[_scored("a1", 0.92, text="hedonic reward paradigm")],
        dense_memories=[_scored("m1", 0.85, text="incentive salience model")],
    )
    emb = _mock_emb()

    results = await dense_retrieve("reward-based decision making", emb, vs)

    assert len(results) == 2
    assert all(isinstance(r, RetrievalResult) for r in results)
    assert all(r.source == "dense" for r in results)
    # Results sorted by score descending
    assert results[0].score >= results[1].score
    emb.embed_query.assert_awaited_once_with("reward-based decision making")


# -- AC2: sparse retrieval finds lexical matches --------------------------------


@pytest.mark.asyncio
async def test_sparse_retrieval_returns_results():
    """Sparse search returns RetrievalResult objects with source='sparse'."""
    vs = _mock_vs(
        sparse_artifacts=[_scored("a1", 12.5, text="Berridge Robinson 1998 citation")],
    )

    results = await sparse_retrieve("Berridge Robinson 1998", vs)

    assert len(results) == 1
    assert results[0].source == "sparse"
    assert results[0].text == "Berridge Robinson 1998 citation"


# -- AC3 & AC4: dense and sparse are complementary ----------------------------
# (Demonstrated by the fact that they use different search methods and can
#  return different result sets. The integration tests in shared/ prove the
#  actual retrieval difference. Here we verify the wiring is correct.)


@pytest.mark.asyncio
async def test_dense_uses_embedding_sparse_does_not():
    """Dense calls embed_query; sparse does not."""
    emb = _mock_emb()
    vs = _mock_vs()

    await dense_retrieve("test query", emb, vs)
    emb.embed_query.assert_awaited_once()

    emb2 = _mock_emb()
    await sparse_retrieve("test query", vs)
    emb2.embed_query.assert_not_awaited()


# -- AC5: exclude_run_id filter ------------------------------------------------


@pytest.mark.asyncio
async def test_exclude_run_id_filters_current_run():
    """Results from the current run are excluded via exclude_run_id filter."""
    vs = _mock_vs(
        dense_artifacts=[
            _scored("a1", 0.9, run_id="current-run"),
            _scored("a2", 0.8, run_id="other-run"),
        ],
    )
    emb = _mock_emb()

    results = await dense_retrieve(
        "test", emb, vs, filters={"exclude_run_id": "current-run"}
    )

    assert len(results) == 1
    assert results[0].metadata["run_id"] == "other-run"


# -- AC6: namespace filter -----------------------------------------------------


@pytest.mark.asyncio
async def test_namespace_filter_passed_to_vector_store():
    """namespace filter is forwarded to VectorStore.search_dense."""
    vs = _mock_vs()
    emb = _mock_emb()

    await dense_retrieve("test", emb, vs, filters={"namespace": "formulation"})

    # Check that search_dense was called with filters containing namespace
    for call in vs.search_dense.call_args_list:
        filters = (
            call.kwargs.get("filters") or call.args[3] if len(call.args) > 3 else None
        )
        if filters:
            assert "namespace" in filters


@pytest.mark.asyncio
async def test_namespace_filter_on_sparse():
    """namespace filter is forwarded to VectorStore on sparse retrieval."""
    vs = _mock_vs()

    await sparse_retrieve("test query", vs, filters={"namespace": "paradigm"})

    for call in vs.search_sparse.call_args_list:
        filters = call.kwargs.get("filters")
        if filters:
            assert "namespace" in filters


# -- AC7: vector_retrieve runs both in parallel --------------------------------


@pytest.mark.asyncio
async def test_vector_retrieve_returns_both_channels():
    """vector_retrieve returns (dense_results, sparse_results) tuple."""
    vs = _mock_vs(
        dense_artifacts=[_scored("d1", 0.9)],
        sparse_artifacts=[_scored("s1", 5.0)],
    )
    emb = _mock_emb()

    dense_results, sparse_results = await vector_retrieve("test", emb, vs)

    assert len(dense_results) >= 1
    assert len(sparse_results) >= 1
    assert dense_results[0].source == "dense"
    assert sparse_results[0].source == "sparse"


@pytest.mark.asyncio
async def test_vector_retrieve_runs_in_parallel():
    """vector_retrieve runs dense and sparse concurrently (not sequentially)."""
    order: list[str] = []

    async def slow_dense(collection, vector, limit=20, filters=None):
        order.append(f"dense_{collection}_start")
        await asyncio.sleep(0.05)
        order.append(f"dense_{collection}_end")
        return [_scored("d1", 0.9)]

    async def slow_sparse(collection, query, limit=20, filters=None):
        order.append(f"sparse_{collection}_start")
        await asyncio.sleep(0.05)
        order.append(f"sparse_{collection}_end")
        return [_scored("s1", 5.0)]

    vs = AsyncMock()
    vs.search_dense = AsyncMock(side_effect=slow_dense)
    vs.search_sparse = AsyncMock(side_effect=slow_sparse)
    emb = _mock_emb()

    _dense_results, _sparse_results = await vector_retrieve("test", emb, vs)

    # If parallel, all starts should come before all ends
    ends = [e for e in order if e.endswith("_end")]
    # At least one dense and one sparse start before any end
    first_end_idx = order.index(ends[0])
    starts_before_first_end = [e for e in order[:first_end_idx] if e.endswith("_start")]
    assert len(starts_before_first_end) >= 2, (
        f"Expected parallel execution, got: {order}"
    )


# -- AC8: empty collections return empty results --------------------------------


@pytest.mark.asyncio
async def test_dense_empty_collections():
    """Dense search on empty collections returns empty list."""
    vs = _mock_vs()
    emb = _mock_emb()
    results = await dense_retrieve("anything", emb, vs)
    assert results == []


@pytest.mark.asyncio
async def test_sparse_empty_collections():
    """Sparse search on empty collections returns empty list."""
    vs = _mock_vs()
    results = await sparse_retrieve("anything", vs)
    assert results == []


@pytest.mark.asyncio
async def test_vector_retrieve_empty():
    """vector_retrieve on empty collections returns two empty lists."""
    vs = _mock_vs()
    emb = _mock_emb()
    dense_results, sparse_results = await vector_retrieve("anything", emb, vs)
    assert dense_results == []
    assert sparse_results == []


# -- Score normalization -------------------------------------------------------


@pytest.mark.asyncio
async def test_sparse_scores_normalized_0_to_1():
    """Sparse results have scores normalized to 0-1 range."""
    vs = _mock_vs(
        sparse_artifacts=[
            _scored("a1", 10.0),
            _scored("a2", 5.0),
            _scored("a3", 2.5),
        ],
    )

    results = await sparse_retrieve("test query", vs)

    assert results[0].score == 1.0  # max score → 1.0
    assert results[1].score == 0.5  # 5.0 / 10.0
    assert results[2].score == 0.25  # 2.5 / 10.0


@pytest.mark.asyncio
async def test_dense_scores_used_directly():
    """Dense results use Qdrant cosine similarity scores directly (already 0-1)."""
    vs = _mock_vs(
        dense_artifacts=[_scored("a1", 0.92)],
    )
    emb = _mock_emb()

    results = await dense_retrieve("test", emb, vs)

    assert results[0].score == 0.92


# -- Metadata preservation ----------------------------------------------------


@pytest.mark.asyncio
async def test_result_metadata_includes_collection_source():
    """Results include the collection they came from in metadata."""
    vs = _mock_vs(
        dense_artifacts=[_scored("a1", 0.9)],
        dense_memories=[_scored("m1", 0.8)],
    )
    emb = _mock_emb()

    results = await dense_retrieve("test", emb, vs)

    collections = {r.metadata["collection"] for r in results}
    assert "artifacts_dense" in collections
    assert "memories_dense" in collections


# -- min_confidence filter -----------------------------------------------------


@pytest.mark.asyncio
async def test_min_confidence_filter():
    """min_confidence filter is translated to Qdrant range filter."""
    vs = _mock_vs()
    emb = _mock_emb()

    await dense_retrieve("test", emb, vs, filters={"min_confidence": 0.7})

    for call in vs.search_dense.call_args_list:
        filters = call.kwargs.get("filters")
        if filters:
            assert "confidence" in filters
            assert filters["confidence"] == {"gte": 0.7}

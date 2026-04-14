"""Dense and sparse vector retrieval channels for the knowledge backbone.

Dense retrieval: embeds query via Voyage AI, searches Qdrant dense collections.
Sparse retrieval: tokenizes query, searches Qdrant sparse collections.
Combined: runs both in parallel via asyncio.gather.
"""

from __future__ import annotations

import asyncio

from shared.embedding import EmbeddingService
from shared.vector_store import ScoredPoint, VectorStore

from decisionlab.knowledge.retrieval.models import RetrievalResult
from decisionlab.knowledge.tokenizer import tokenize_to_sparse

_DENSE_COLLECTIONS = ("artifacts_dense", "memories_dense")
_SPARSE_COLLECTIONS = ("artifacts_sparse", "memories_sparse")


def _translate_filters(filters: dict | None) -> tuple[dict | None, str | None]:
    """Separate user-facing filters into Qdrant filters + exclude_run_id.

    Returns (qdrant_filters, exclude_run_id).
    """
    if not filters:
        return None, None

    qdrant = {}
    exclude_run_id = None

    for key, value in filters.items():
        if key == "exclude_run_id":
            exclude_run_id = value
        elif key == "min_confidence":
            qdrant["confidence"] = {"gte": value}
        else:
            qdrant[key] = value

    return qdrant or None, exclude_run_id


def _to_results(
    points: list[ScoredPoint],
    source: str,
    collection: str,
    exclude_run_id: str | None = None,
) -> list[RetrievalResult]:
    """Convert Qdrant ScoredPoints to RetrievalResults, applying post-filters."""
    results = []
    for p in points:
        if exclude_run_id and p.payload.get("run_id") == exclude_run_id:
            continue
        results.append(
            RetrievalResult(
                text=p.payload.get("text_preview", ""),
                score=p.score,
                source=source,
                metadata={**p.payload, "collection": collection},
            )
        )
    return results


async def dense_retrieve(
    query: str,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
    limit: int = 20,
    filters: dict | None = None,
) -> list[RetrievalResult]:
    """Retrieve via dense (semantic) vector search across both collections.

    Embeds query with input_type="query", searches artifacts_dense and
    memories_dense, merges results sorted by score descending.
    """
    query_vec = await embedding_service.embed_query(query)
    qdrant_filters, exclude_run_id = _translate_filters(filters)

    coros = [
        vector_store.search_dense(coll, query_vec, limit=limit, filters=qdrant_filters)
        for coll in _DENSE_COLLECTIONS
    ]
    batches = await asyncio.gather(*coros)

    results: list[RetrievalResult] = []
    for coll, points in zip(_DENSE_COLLECTIONS, batches):
        results.extend(_to_results(points, "dense", coll, exclude_run_id))

    results.sort(key=lambda r: r.score, reverse=True)
    return results


async def sparse_retrieve(
    query: str,
    vector_store: VectorStore,
    limit: int = 20,
    filters: dict | None = None,
) -> list[RetrievalResult]:
    """Retrieve via sparse (lexical/BM25) vector search across both collections.

    Tokenizes query, searches artifacts_sparse and memories_sparse,
    merges results with scores normalized to 0-1.
    """
    indices, values = tokenize_to_sparse(query)
    if not indices:
        return []

    qdrant_filters, exclude_run_id = _translate_filters(filters)

    coros = [
        vector_store.search_sparse(
            coll, indices, values, limit=limit, filters=qdrant_filters
        )
        for coll in _SPARSE_COLLECTIONS
    ]
    batches = await asyncio.gather(*coros)

    raw: list[RetrievalResult] = []
    for coll, points in zip(_SPARSE_COLLECTIONS, batches):
        raw.extend(_to_results(points, "sparse", coll, exclude_run_id))

    if not raw:
        return []

    # Normalize scores to 0-1 (divide by max)
    max_score = max(r.score for r in raw)
    if max_score > 0:
        for r in raw:
            r.score = r.score / max_score

    raw.sort(key=lambda r: r.score, reverse=True)
    return raw


async def vector_retrieve(
    query: str,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
    limit: int = 20,
    filters: dict | None = None,
) -> tuple[list[RetrievalResult], list[RetrievalResult]]:
    """Run dense and sparse retrieval in parallel.

    Returns (dense_results, sparse_results) as separate lists for RRF fusion.
    """
    dense_results, sparse_results = await asyncio.gather(
        dense_retrieve(query, embedding_service, vector_store, limit, filters),
        sparse_retrieve(query, vector_store, limit, filters),
    )
    return dense_results, sparse_results

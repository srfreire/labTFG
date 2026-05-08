"""Dense and sparse vector retrieval channels for the knowledge backbone.

Dense retrieval: embeds query via Voyage AI, searches Qdrant dense collections.
Sparse retrieval: passes raw query text to Qdrant's native BM25 sparse search.
Combined: runs both in parallel via asyncio.gather.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from decisionlab.knowledge.retrieval.models import RetrievalResult
from decisionlab.knowledge.retrieval.query_rewriter import rewrite as _rewrite
from shared.embedding import EmbeddingService
from shared.vector_store import ScoredPoint, VectorStore

logger = logging.getLogger(__name__)

_DENSE_COLLECTIONS = ("memories_dense",)
_SPARSE_COLLECTIONS = ("memories_sparse",)


def _translate_filters(filters: dict | None) -> dict | None:
    """Convert user-facing filters into Qdrant-shape filters.

    ``exclude_run_id`` is folded into the special ``_exclude`` key so
    Qdrant applies it as a server-side ``must_not`` condition (rather
    than the prior Python post-filter loop).
    """
    if not filters:
        return None

    qdrant: dict = {}
    for key, value in filters.items():
        if key == "exclude_run_id":
            qdrant.setdefault("_exclude", {})["run_id"] = value
        elif key == "min_confidence":
            qdrant["confidence"] = {"gte": value}
        else:
            qdrant[key] = value
    return qdrant or None


def _to_results(
    points: list[ScoredPoint],
    source: str,
    collection: str,
) -> list[RetrievalResult]:
    """Convert Qdrant ScoredPoints to RetrievalResults."""
    results = []
    for p in points:
        meta = {**p.payload, "collection": collection}
        if "created_at" in meta and "run_date" not in meta:
            meta["run_date"] = meta["created_at"]
        results.append(
            RetrievalResult(
                text=p.payload.get("text_preview", ""),
                score=p.score,
                source=source,
                metadata=meta,
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

    Embeds query with input_type="query", searches ``memories_dense``,
    sorts results by score descending. P4-002 dropped the parallel
    ``artifacts_dense`` channel.
    """
    query_vec = await embedding_service.embed_query(query)
    qdrant_filters = _translate_filters(filters)

    coros = [
        vector_store.search_dense(coll, query_vec, limit=limit, filters=qdrant_filters)
        for coll in _DENSE_COLLECTIONS
    ]
    batches = await asyncio.gather(*coros)

    results: list[RetrievalResult] = []
    for coll, points in zip(_DENSE_COLLECTIONS, batches, strict=False):
        results.extend(_to_results(points, "dense", coll))

    results.sort(key=lambda r: r.score, reverse=True)
    return results


async def sparse_retrieve(
    query: str,
    vector_store: VectorStore,
    limit: int = 20,
    filters: dict | None = None,
) -> list[RetrievalResult]:
    """Retrieve via sparse (lexical/BM25) vector search.

    Passes raw query text to Qdrant's native BM25 search over
    ``memories_sparse``; scores are normalized to 0-1. P4-002 dropped
    the parallel ``artifacts_sparse`` channel.
    """
    if not query.strip():
        return []

    qdrant_filters = _translate_filters(filters)

    coros = [
        vector_store.search_sparse(coll, query, limit=limit, filters=qdrant_filters)
        for coll in _SPARSE_COLLECTIONS
    ]
    batches = await asyncio.gather(*coros)

    results: list[RetrievalResult] = []
    for coll, points in zip(_SPARSE_COLLECTIONS, batches, strict=False):
        results.extend(_to_results(points, "sparse", coll))

    if not results:
        return []

    max_score = max(r.score for r in results)
    if max_score > 0:
        results = [replace(r, score=r.score / max_score) for r in results]

    results.sort(key=lambda r: r.score, reverse=True)
    return results


async def vector_retrieve(
    query: str,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
    limit: int = 20,
    filters: dict | None = None,
    *,
    client=None,
) -> tuple[list[RetrievalResult], list[RetrievalResult]]:
    """Run dense and sparse retrieval in parallel.

    When *client* is supplied the query is run through the rewriter
    first; the dense path then embeds only the focal concept (cleaner
    semantic signal) while the sparse path uses ``query + keywords``
    (broader BM25 lemma coverage). With no *client*, both paths receive
    the raw query — the pre-rewriter behaviour.

    Returns (dense_results, sparse_results) as separate lists for RRF
    fusion. Returns empty lists on any connection or service error so
    callers degrade gracefully.
    """
    try:
        dense_query = query
        sparse_query = query
        if client is not None:
            rewritten = await _rewrite(query, client=client)
            if rewritten.focal_concept:
                dense_query = rewritten.focal_concept
            if rewritten.keywords:
                sparse_query = f"{query} {' '.join(rewritten.keywords)}"

        dense_results, sparse_results = await asyncio.gather(
            dense_retrieve(
                dense_query, embedding_service, vector_store, limit, filters
            ),
            sparse_retrieve(sparse_query, vector_store, limit, filters),
        )
        return dense_results, sparse_results
    except Exception as exc:
        logger.error(
            "vector_retrieve failed (%s): %s", type(exc).__name__, exc, exc_info=True
        )
        return [], []

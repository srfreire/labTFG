"""Reciprocal Rank Fusion and Voyage AI reranking pipeline.

Merges results from 3 retrieval channels (KG, dense, sparse) via RRF,
then reranks fused results using Voyage AI for final relevance ordering.
"""

from __future__ import annotations

import re

from shared.embedding import EmbeddingService

from decisionlab.knowledge.retrieval.models import RetrievalResult


def _normalize_text(text: str) -> str:
    """Normalize whitespace and strip for deduplication comparison."""
    return re.sub(r"\s+", " ", text.strip())


def _dedup_key(text: str) -> str:
    """First 200 characters of normalized text, used for deduplication."""
    return _normalize_text(text)[:200]


def rrf_fuse(
    result_lists: list[list[RetrievalResult]],
    k: int = 60,
    top_n: int = 30,
) -> list[RetrievalResult]:
    """Fuse multiple ranked result lists using Reciprocal Rank Fusion.

    RRF_score(d) = Σ_r 1/(k + rank_r(d)), where rank starts at 1.
    Deduplicates by comparing the first 200 characters of normalized text.
    """
    if not result_lists:
        return []

    # Map: dedup_key -> (rrf_score, best_text, set_of_sources, merged_metadata)
    fused: dict[str, tuple[float, str, set[str], dict]] = {}

    for ranked_list in result_lists:
        for rank_idx, result in enumerate(ranked_list):
            rank = rank_idx + 1  # ranks start at 1
            rrf_score = 1.0 / (k + rank)
            key = _dedup_key(result.text)

            if key in fused:
                prev_score, prev_text, sources, meta = fused[key]
                sources.add(result.source)
                merged_meta = {**result.metadata, **meta}
                fused[key] = (prev_score + rrf_score, prev_text, sources, merged_meta)
            else:
                fused[key] = (
                    rrf_score,
                    result.text,
                    {result.source},
                    dict(result.metadata),
                )

    # Build sorted results
    entries = sorted(fused.values(), key=lambda e: e[0], reverse=True)[:top_n]

    return [
        RetrievalResult(
            text=text,
            score=score,
            source="fused",
            metadata={**meta, "sources": sorted(sources)},
        )
        for score, text, sources, meta in entries
    ]


async def rerank_results(
    query: str,
    results: list[RetrievalResult],
    embedding_service: EmbeddingService,
    top_k: int = 10,
    threshold: float = 0.3,
) -> list[RetrievalResult]:
    """Rerank results using Voyage AI, filtering below threshold."""
    if not results:
        return []

    texts = [r.text for r in results]
    ranked = await embedding_service.rerank(query=query, documents=texts, top_k=top_k)

    reranked: list[RetrievalResult] = []
    for r in ranked:
        if r.score < threshold:
            continue
        if r.index >= len(results):
            continue
        original = results[r.index]
        reranked.append(
            RetrievalResult(
                text=original.text,
                score=r.score,
                source=original.source,
                metadata={
                    **original.metadata,
                    "reranker_score": r.score,
                    "pre_rerank_score": original.score,
                },
            )
        )

    return reranked


async def fuse_and_rerank(
    query: str,
    kg_results: list[RetrievalResult],
    dense_results: list[RetrievalResult],
    sparse_results: list[RetrievalResult],
    embedding_service: EmbeddingService,
    rrf_k: int = 60,
    rrf_top_n: int = 30,
    rerank_top_k: int = 10,
    rerank_threshold: float = 0.3,
) -> list[RetrievalResult]:
    """Fuse 3 retrieval channels via RRF, then rerank with Voyage AI."""
    fused = rrf_fuse([kg_results, dense_results, sparse_results], k=rrf_k, top_n=rrf_top_n)
    if not fused:
        return []
    return await rerank_results(query, fused, embedding_service, rerank_top_k, rerank_threshold)

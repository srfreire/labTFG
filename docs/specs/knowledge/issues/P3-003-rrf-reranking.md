---
id: P3-003
title: Implement Reciprocal Rank Fusion and Voyage AI reranking pipeline
status: todo
kind: strike
phase: 3
heat: fusion
priority: 2
blocked_by: [P3-001, P3-002]
created: 2026-04-14
updated: 2026-04-14
---

# P3-003: Implement Reciprocal Rank Fusion and Voyage AI reranking pipeline

## Objective
Merge results from the 3 retrieval channels (KG, dense, sparse) using Reciprocal Rank Fusion, then rerank the fused results using Voyage AI's reranker for final relevance ordering.

## Requirements
- Module: `phase1-pablo/src/decisionlab/knowledge/retrieval/fusion.py`

- **RRF Fusion:**
  `rrf_fuse(result_lists: list[list[RetrievalResult]], k: int = 60, top_n: int = 30) -> list[RetrievalResult]`
  - Input: list of ranked result lists (one per retrieval channel)
  - Formula: `RRF_score(d) = Σ_r 1/(k + rank_r(d))` where rank starts at 1
  - Deduplication: if the same text appears in multiple channels, merge into single entry with combined RRF score. Track which channels contributed in `metadata.sources: list[str]`
  - Text matching for dedup: normalize whitespace, strip leading/trailing whitespace, compare. Two passages are "same" if their first 200 characters match after normalization.
  - Output: top_n results sorted by RRF score descending
  - Pure function — no async, no external calls

- **Reranking:**
  `async rerank_results(query: str, results: list[RetrievalResult], embedding_service: EmbeddingService, top_k: int = 10, threshold: float = 0.3) -> list[RetrievalResult]`
  - Extract text from each RetrievalResult
  - Call `embedding_service.rerank(query, texts, top_k=top_k)`
  - Filter results below `threshold` score
  - Map reranked results back to RetrievalResult objects, updating `score` to reranker score
  - Preserve original metadata + add `reranker_score` and `pre_rerank_score` to metadata

- **Combined fusion+rerank:**
  `async fuse_and_rerank(query: str, kg_results: list[RetrievalResult], dense_results: list[RetrievalResult], sparse_results: list[RetrievalResult], embedding_service: EmbeddingService, rrf_k: int = 60, rrf_top_n: int = 30, rerank_top_k: int = 10, rerank_threshold: float = 0.3) -> list[RetrievalResult]`
  - Calls `rrf_fuse` then `rerank_results`
  - Returns final reranked list

## Acceptance Criteria
- [ ] AC1: RRF fusion of 3 lists with overlapping documents produces correct scores — a document in all 3 lists scores `3/(k+1)` (highest possible for rank-1 in all)
- [ ] AC2: RRF deduplication merges the same passage from dense and sparse into one entry with `metadata.sources = ["dense", "sparse"]`
- [ ] AC3: A document ranked #1 in one channel and absent from others scores `1/(k+1) ≈ 0.0164`, while a document ranked #5 in all 3 channels scores `3/(k+5) ≈ 0.0462` — multi-channel presence wins
- [ ] AC4: Reranking reorders results — a semantically relevant document with low RRF score can move up after reranking
- [ ] AC5: Threshold filtering removes results with reranker score < 0.3
- [ ] AC6: Empty input lists produce empty output without errors
- [ ] AC7: `fuse_and_rerank` end-to-end: 3 channels with 20 results each → RRF top-30 → rerank top-10 → final list of <=10 results

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/retrieval/fusion.py` — new file

## Context
Phase spec: `docs/specs/knowledge/phase-3-retrieval-crag.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `fusion`
Depends on P3-001 and P3-002 for the RetrievalResult dataclass and retrieval channel outputs.
Uses `EmbeddingService` from P1-004 for reranking.

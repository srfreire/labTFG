---
id: P3-002
title: Implement dense vector and sparse lexical retrieval channels
status: todo
kind: strike
phase: 3
heat: retrieval
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-14
---

# P3-002: Implement dense vector and sparse lexical retrieval channels

## Objective
Build the dense (semantic) and sparse (lexical/BM25) retrieval channels that query Qdrant collections and return ranked results for fusion.

## Requirements
- Module: `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py`

- **Dense retrieval:**
  `async dense_retrieve(query: str, embedding_service: EmbeddingService, vector_store: VectorStore, limit: int = 20, filters: dict | None = None) -> list[RetrievalResult]`
  - Embed query via `embedding_service.embed_query(query)` (uses `input_type="query"`)
  - Search both `artifacts_dense` and `memories_dense` collections
  - Merge results from both collections, keeping collection source in metadata
  - Apply payload filters if provided: `namespace`, `min_confidence` (gte), `exclude_run_id` (to avoid self-retrieval within current run)
  - Convert Qdrant `ScoredPoint` to `RetrievalResult` with `source="dense"`
  - Score: use Qdrant cosine similarity score directly (already 0-1)

- **Sparse retrieval:**
  `async sparse_retrieve(query: str, vector_store: VectorStore, limit: int = 20, filters: dict | None = None) -> list[RetrievalResult]`
  - Tokenize query: lowercase, split on whitespace/punctuation, remove English stopwords (hardcoded small set: the, a, an, is, are, in, on, of, for, to, and, or, with, by, from, at)
  - Build sparse vector: term indices (hash of each token) + term frequencies as values
  - Search both `artifacts_sparse` and `memories_sparse` collections
  - Merge results, convert to `RetrievalResult` with `source="sparse"`
  - Score: normalize Qdrant sparse scores to 0-1 range (divide by max score in result set, or cap at 1.0)

- **Tokenizer utility:**
  `tokenize_to_sparse(text: str) -> tuple[list[int], list[float]]`
  - Returns (indices, values) suitable for Qdrant sparse vector upsert/search
  - Same function used by P2-003 (indexer) for indexing and by this module for queries — must produce consistent tokenization
  - Place in `phase1-pablo/src/decisionlab/knowledge/tokenizer.py` for shared access

- **Combined convenience function:**
  `async vector_retrieve(query: str, embedding_service: EmbeddingService, vector_store: VectorStore, limit: int = 20, filters: dict | None = None) -> tuple[list[RetrievalResult], list[RetrievalResult]]`
  - Runs dense and sparse in parallel via `asyncio.gather`
  - Returns (dense_results, sparse_results) as separate lists for RRF fusion

## Acceptance Criteria
- [ ] AC1: Dense search for "reward-based decision making" returns chunks from hedonic/incentive-salience paradigm reports (semantic match)
- [ ] AC2: Sparse search for "Berridge Robinson 1998" returns chunks containing that exact citation (lexical match)
- [ ] AC3: Dense search does NOT find an exact DOI string that sparse search finds (demonstrates complementary retrieval)
- [ ] AC4: Sparse search does NOT find semantically related content that dense search finds (demonstrates complementary retrieval)
- [ ] AC5: `exclude_run_id` filter prevents retrieving chunks from the current run
- [ ] AC6: `namespace` filter restricts results to the specified namespace only
- [ ] AC7: `vector_retrieve` runs both channels in parallel (total time ≈ max of the two, not sum)
- [ ] AC8: Empty collections return empty results without errors

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py` — new file
- `phase1-pablo/src/decisionlab/knowledge/tokenizer.py` — new file, shared sparse tokenizer

## Context
Phase spec: `docs/specs/knowledge/phase-3-retrieval-crag.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `retrieval`
Uses `VectorStore` from P1-003 and `EmbeddingService` from P1-004.
Can run in parallel with P3-001 (KG retrieval) — they are independent retrieval channels.

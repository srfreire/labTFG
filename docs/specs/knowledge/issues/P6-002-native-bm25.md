---
id: P6-002
title: Replace MD5 sparse tokenizer with Qdrant native BM25
status: todo
kind: strike
phase: 6
heat: schema
priority: 2
blocked_by: []
created: 2026-04-16
updated: 2026-04-16
---

# P6-002: Replace MD5 sparse tokenizer with Qdrant native BM25

## Objective
Replace the custom MD5-hash sparse tokenizer with Qdrant's native BM25 support (v1.15.2+). This gives us proper IDF weighting, TF saturation, document length normalization, and stemming — all computed server-side by Qdrant. The custom `tokenizer.py` becomes unnecessary.

## Background
Current sparse vectors use MD5-hashed token indices with raw term frequency counts. This means:
- No IDF: "the" and "dopamine" get similar weights
- No TF saturation: a word repeated 50x gets 50x the score
- No document length normalization
- No stemming: "running" won't match "run"

Qdrant native BM25 handles all of this server-side. We just send raw text.

## Requirements

### Update sparse collection config
- Change `SparseVectorParams(index=SparseIndexParams())` to include `modifier=Modifier.IDF` so Qdrant computes IDF server-side
- Collections affected: `artifacts_sparse`, `memories_sparse`
- Since collections must be recreated to change config, add a migration step or document the recreation

### Update VectorStore API
- `upsert_sparse` should accept raw text instead of pre-computed indices/values
- Qdrant native BM25 uses `Document(text=..., model="Qdrant/bm25")` as the vector input
- `search_sparse` should accept query text instead of pre-computed indices/values
- Keep the old signature available with a deprecation warning, or update all callers in one pass

### Update indexer
- `phase1-pablo/src/decisionlab/knowledge/indexer.py`: remove calls to `tokenize_to_sparse()`, pass raw text chunks directly to the new `upsert_sparse`

### Update retrieval
- `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py`: remove calls to `tokenize_to_sparse()`, pass raw query text to the new `search_sparse`

### Delete tokenizer
- Delete `phase1-pablo/src/decisionlab/knowledge/tokenizer.py`
- Remove all imports of `tokenize_to_sparse` across the codebase

### Update tests
- Update sparse vector tests to use text-based API
- Remove tokenizer unit tests

## Acceptance Criteria
- [ ] Sparse collections use `modifier=Modifier.IDF` in config
- [ ] `upsert_sparse` accepts raw text, not pre-computed indices/values
- [ ] `search_sparse` accepts query text, not pre-computed indices/values
- [ ] `tokenizer.py` deleted, no imports of `tokenize_to_sparse` in codebase
- [ ] Sparse search returns results with proper BM25 scoring (rare terms weighted higher)
- [ ] All existing tests pass

## Files Likely Affected
- `shared/shared/vector_store.py` — collection config, upsert_sparse, search_sparse API change
- `phase1-pablo/src/decisionlab/knowledge/indexer.py` — remove tokenize_to_sparse calls
- `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py` — remove tokenize_to_sparse calls
- `phase1-pablo/src/decisionlab/knowledge/tokenizer.py` — DELETE
- `shared/tests/` — update sparse vector tests
- `phase1-pablo/tests/` — remove tokenizer tests, update integration tests
- `docs/knowledge-architecture.md` — update Qdrant section (MD5 hash → native BM25), update sparse description, remove tokenizer references

## Context
Phase: 6 — Schema Cleanse
Heat: `schema`
The custom tokenizer was a pragmatic shortcut during initial implementation. Qdrant native BM25 (available since v1.15.2, our Docker image uses `latest`) gives us proper BM25 for free.

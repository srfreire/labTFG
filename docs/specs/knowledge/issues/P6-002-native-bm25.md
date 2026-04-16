---
id: P6-002
title: Replace MD5 sparse tokenizer with Qdrant native BM25
status: done
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
- [x] Sparse collections use `modifier=Modifier.IDF` in config
- [x] `upsert_sparse` accepts raw text, not pre-computed indices/values
- [x] `search_sparse` accepts query text, not pre-computed indices/values
- [x] `tokenizer.py` deleted, no imports of `tokenize_to_sparse` in codebase
- [x] Sparse search returns results with proper BM25 scoring (rare terms weighted higher)
- [x] All existing tests pass

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

## Completion Summary

**Commit:** `9660544` — bundled into the P6-001 completion commit on main (P6-001's stale strike worktree left files uncommitted, so P6-002's squash-merge landed under that commit message). Code on `strike/schema-P6-002` was developed as 5 commits: `f708d4a` (main feature), `d12794a` / `9d2f542` / `cfca8ae` (simplifier passes), `9455100` (reviewer fix).

### What was built
- `shared/shared/vector_store.py`: sparse collections are created with `modifier=Modifier.IDF`. `upsert_sparse(collection, id, text, payload)` and `search_sparse(collection, query, limit, filters)` now wrap raw text in `Document(text=..., model="Qdrant/bm25")` — FastEmbed tokenizes client-side, Qdrant scores BM25 + IDF server-side. Added `BM25_MODEL` constant.
- `phase1-pablo/src/decisionlab/knowledge/indexer.py`: removed the `tokenize_to_sparse` / `sparse_vecs` loop; chunk text is forwarded directly to `upsert_sparse`.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py`: `sparse_retrieve` passes the raw query, early-returns on empty input, uses `dataclasses.replace` for score normalization, and logs exception type + traceback on `vector_retrieve` failure so cold-start FastEmbed issues are diagnosable.
- Deleted `phase1-pablo/src/decisionlab/knowledge/tokenizer.py` and `phase1-pablo/tests/knowledge/test_tokenizer.py` — no remaining callers.
- `shared/tests/test_vector_store.py`: sparse tests use the text API; added `test_sparse_bm25_idf_ranks_rare_terms_higher` which seeds a 20-doc filler corpus (parallelized via `asyncio.gather`) so IDF statistics matter, then verifies that a rare term wins over frequent fillers.
- `shared/pyproject.toml`: dependency bumped to `qdrant-client[fastembed]>=1.15.2` so the `Qdrant/bm25` FastEmbed model is available.
- `docs/knowledge-architecture.md`: sparse collection rows now say "Qdrant native BM25, `modifier=IDF`"; added a "Native BM25 over a custom tokenizer" callout; the Layer 3 retrieval step describes sending raw text rather than pre-hashed indices.

### Files created/modified
- `shared/shared/vector_store.py` — IDF modifier + text-based sparse API
- `shared/pyproject.toml` — `qdrant-client[fastembed]>=1.15.2`
- `shared/tests/test_vector_store.py` — updated sparse tests + new BM25 IDF ranking test
- `phase1-pablo/src/decisionlab/knowledge/indexer.py` — pass chunk text to `upsert_sparse`
- `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py` — pass query to `search_sparse`, wider error logging
- `phase1-pablo/tests/knowledge/test_vector_retrieval.py` — mock signatures match new API
- `phase1-pablo/src/decisionlab/knowledge/tokenizer.py` — **deleted**
- `phase1-pablo/tests/knowledge/test_tokenizer.py` — **deleted**
- `docs/knowledge-architecture.md` — MD5 references → native BM25

### Decisions
- Used the `qdrant-client[fastembed]` extra (rather than adding `fastembed` as a standalone dep). FastEmbed ships a `Qdrant/bm25` model that uses py-rust-stemmers — no large model download, so the extra is lightweight.
- Did not add a deprecation shim for the old `(indices, values)` signature. The spec allowed either approach; all call sites were updated in one pass, so the extra surface was unnecessary.
- Did not write a migration script. The pre-existing `init_collections` is idempotent against missing collections only, not config changes — so sparse collections need to be dropped and re-created on first run after this change. Left as an operator step per the spec.
- Kept the existing `except Exception` guard in `vector_retrieve` (graceful-degradation path is covered by `test_vector_retrieve_never_raises` and `test_qdrant_down_neo4j_up_vector_retrieve_returns_empty`), but widened the log line to include `type(exc).__name__` and `exc_info=True` so FastEmbed cold-start errors surface in logs.

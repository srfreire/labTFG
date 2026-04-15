---
id: BUG-001
title: Run Voyage AI integration tests with live API key
status: done
kind: mend
phase: 1
heat: vector
priority: 1
blocked_by: []
created: 2026-04-15
updated: 2026-04-15
verified: 2026-04-15
---

# BUG-001: Run Voyage AI integration tests with live API key

## Problem
P1-004 (Voyage AI EmbeddingService) was implemented without `VOYAGE_API_KEY` available. All 6 acceptance criteria tests exist in `shared/tests/test_embedding.py` but skip when the key is absent. The service has never been verified against the live API.

## Steps to Reproduce
```bash
cd shared && uv run pytest tests/test_embedding.py -v
# All 6 tests skip with "VOYAGE_API_KEY not set"
```

## Expected Behavior
All 6 tests pass with a valid `VOYAGE_API_KEY`:
- AC1: `embed_texts(["hello world"])` → 1 vector of length 1024
- AC2: 200 texts auto-batches into 2 requests, returns 200 vectors
- AC3: `embed_query("test")` → single vector of length 1024
- AC4: `rerank` scores Q-learning document highest
- AC5: `embed_texts([])` → [] without API call
- AC6: `rerank("query", [])` → [] without API call

## Fix
1. Set `VOYAGE_API_KEY` in `.env`
2. Run `cd shared && uv run pytest tests/test_embedding.py -v`
3. If any test fails, fix the EmbeddingService implementation
4. Check P1-004 acceptance criteria once all pass

## Files
- `shared/tests/test_embedding.py` — 6 integration tests
- `shared/shared/embedding.py` — EmbeddingService under test

## Completion Summary

**Result:** All 6 tests pass — no code changes required.

### What was broken
- EmbeddingService had never been verified against the live Voyage API because `VOYAGE_API_KEY` was unavailable during P1-004 implementation.

### Root cause
- Missing API key, not a code defect.

### Tests verified
- `test_embed_single_text` — AC1: single text → 1 vector of length 1024
- `test_embed_auto_batches` — AC2: 200 texts auto-batched → 200 vectors
- `test_embed_query` — AC3: single query → vector of length 1024
- `test_rerank` — AC4: Q-learning document ranked highest
- `test_embed_empty` — AC5: empty input → [] without API call
- `test_rerank_empty` — AC6: empty documents → [] without API call

### Fix applied
- None needed. Implementation is correct as written.

### Files modified
- `docs/specs/knowledge/issues/BUG-001-voyage-api-tests.md` — status → done

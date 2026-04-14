---
id: BUG-001
title: Run Voyage AI integration tests with live API key
status: todo
kind: mend
phase: 1
heat: vector
priority: 1
blocked_by: []
created: 2026-04-15
updated: 2026-04-15
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

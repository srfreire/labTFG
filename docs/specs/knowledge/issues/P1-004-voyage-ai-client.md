---
id: P1-004
title: Implement Voyage AI embedding and reranking client
status: done
kind: strike
phase: 1
heat: vector
priority: 2
blocked_by: [P1-003]
created: 2026-04-14
updated: 2026-04-14
---

# P1-004: Implement Voyage AI embedding and reranking client

## Objective
Create a wrapper around the Voyage AI SDK that provides async embedding and reranking with automatic batching, for use by the Memory Agent and retrieval system.

## Requirements
- `voyageai` Python SDK as dependency
- `EmbeddingService` class in `shared/embedding.py`:
  - `__init__(api_key: str)` — initializes Voyage client
  - `async embed_texts(texts: list[str], input_type: str = "document") -> list[list[float]]`
    - Model: `voyage-3` (1024 dimensions)
    - Auto-batches: Voyage limit is 128 texts per request; split larger inputs into batches, await all, concatenate results
    - `input_type` parameter: "document" for indexing, "query" for search queries (Voyage optimizes differently)
  - `async embed_query(query: str) -> list[float]`
    - Convenience method: calls `embed_texts([query], input_type="query")`, returns single vector
  - `async rerank(query: str, documents: list[str], top_k: int = 10) -> list[RankedResult]`
    - Model: `rerank-2`
    - Returns results sorted by relevance score descending
    - Handles empty documents list gracefully (returns [])
  - `RankedResult` dataclass: `index: int, score: float, document: str`

- Error handling:
  - Rate limit errors: retry with exponential backoff (max 3 retries)
  - Empty input: return [] without API call
  - API errors: raise with clear message including model name and input size

## Acceptance Criteria
- [ ] AC1: `embed_texts(["hello world"])` returns a list containing one vector of length 1024
- [ ] AC2: `embed_texts` with 200 texts auto-batches into 2 requests (128 + 72) and returns 200 vectors
- [ ] AC3: `embed_query("test")` returns a single vector of length 1024
- [ ] AC4: `rerank("Q-learning", ["Q-learning convergence", "weather forecast", "reinforcement learning"])` returns 3 results with the Q-learning document scoring highest
- [ ] AC5: `embed_texts([])` returns [] without making an API call
- [ ] AC6: `rerank("query", [])` returns [] without making an API call

## Files Likely Affected
- `shared/shared/embedding.py` — new file, EmbeddingService class
- `shared/pyproject.toml` — add `voyageai` dependency

## Context
Phase spec: `docs/specs/knowledge/phase-1-infrastructure.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `vector`
Depends on P1-003 because integration tests may use both VectorStore + EmbeddingService together, and both modify `shared/pyproject.toml`.

## Completion Summary

**Commit:** `0351e27` — `feat[shared]: implement Voyage AI EmbeddingService (P1-004)`

> **Warning:** Integration tests were NOT run — `VOYAGE_API_KEY` was not available at implementation time. All 6 AC tests exist in `shared/tests/test_embedding.py` and skip gracefully when the key is absent. Before relying on this service, set `VOYAGE_API_KEY` and run `uv run pytest tests/test_embedding.py` to verify against the live API.

### What was built
- `EmbeddingService` class wrapping Voyage AI AsyncClient with auto-batching (128 texts/request)
- `embed_texts()` with `input_type` parameter and `asyncio.gather` for parallel batches
- `embed_query()` convenience method with defensive guard
- `rerank()` returning sorted `RankedResult` list
- Built-in retry via SDK (3 retries, exponential backoff for rate limits)
- Empty-input guards on `embed_texts` and `rerank` (return [] without API call)
- Wired into `shared.init()`/`shutdown()` lifecycle as `shared.embeddings` singleton
- Warning logged when `VOYAGE_API_KEY` is absent (graceful degradation)

### Files created/modified
- `shared/shared/embedding.py` — EmbeddingService + RankedResult dataclass
- `shared/shared/settings.py` — added `VOYAGE_API_KEY` setting
- `shared/shared/__init__.py` — wired `embeddings` into init/shutdown
- `shared/pyproject.toml` — added `voyageai>=0.3`
- `shared/tests/test_embedding.py` — 6 integration tests (AC1–AC6)

### Decisions
- Relied on SDK's built-in tenacity retry (rate limit, timeout, 503) instead of custom retry logic
- Used `asyncio.gather` for concurrent batch embedding rather than sequential requests
- `VOYAGE_API_KEY` defaults to empty string — `EmbeddingService` only instantiated when key is present

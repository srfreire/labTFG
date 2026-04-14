---
id: P1-004
title: Implement Voyage AI embedding and reranking client
status: todo
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

---
id: P1-003
title: Create Qdrant vector store collections and async client
status: todo
kind: strike
phase: 1
heat: vector
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-14
---

# P1-003: Create Qdrant vector store collections and async client

## Objective
Set up 4 Qdrant collections (dense + sparse for both artifacts and memories) and implement an async Python client class for vector operations.

## Requirements
- 4 collections created on init:
  - `artifacts_dense`: 1024 dimensions, cosine distance — stores Voyage AI embeddings of pipeline artifact chunks
  - `artifacts_sparse`: sparse vectors — stores BM25-equivalent representations of same chunks
  - `memories_dense`: 1024 dimensions, cosine distance — stores Voyage AI embeddings of extracted memory facts
  - `memories_sparse`: sparse vectors — stores BM25-equivalent representations of same facts

- Each point's payload schema:
  - `entity_id`: str — memory_id (UUID) or artifact S3 key
  - `namespace`: str — paradigm/formulation/model/simulation/meta
  - `source_stage`: str — which pipeline stage
  - `run_id`: str — pipeline run UUID
  - `importance`: float — 1-10
  - `confidence`: float — 0-1
  - `created_at`: str (ISO 8601)
  - `text_preview`: str — first 200 chars for debugging

- `VectorStore` class in `shared/vector_store.py`:
  - `__init__(url)` — creates `AsyncQdrantClient`
  - `async init_collections()` — creates collections if they don't exist (idempotent)
  - `async upsert_dense(collection: str, id: str, vector: list[float], payload: dict)`
  - `async upsert_sparse(collection: str, id: str, indices: list[int], values: list[float], payload: dict)`
  - `async search_dense(collection: str, vector: list[float], limit: int = 20, filters: dict | None = None) -> list[ScoredPoint]`
  - `async search_sparse(collection: str, indices: list[int], values: list[float], limit: int = 20, filters: dict | None = None) -> list[ScoredPoint]`
  - `async delete(collection: str, ids: list[str])`
  - `async close()`
  - `ScoredPoint` dataclass: id, score, payload

- Qdrant filters mapped from dict: `{"namespace": "paradigm", "confidence": {"gte": 0.5}}` → Qdrant `Filter` objects

## Acceptance Criteria
- [ ] AC1: `init_collections()` creates all 4 collections on fresh Qdrant, and is idempotent
- [ ] AC2: Can upsert a dense vector with payload into `artifacts_dense`, search with a query vector, and get the point back with correct payload
- [ ] AC3: Can upsert a sparse vector into `artifacts_sparse`, search with sparse query, and get the point back
- [ ] AC4: Filter by namespace works: upsert 3 points with different namespaces, search with namespace filter returns only matching points
- [ ] AC5: Filter by confidence threshold works: `{"confidence": {"gte": 0.7}}` excludes low-confidence points
- [ ] AC6: `delete()` removes points and subsequent search does not return them

## Files Likely Affected
- `shared/shared/vector_store.py` — new file, VectorStore class
- `shared/pyproject.toml` — add `qdrant-client` dependency

## Context
Phase spec: `docs/specs/knowledge/phase-1-infrastructure.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `vector`

---
id: P2-003
title: Build embedding and Qdrant indexing pipeline for artifacts and facts
status: todo
kind: strike
phase: 2
heat: indexing
priority: 2
blocked_by: [P2-001]
created: 2026-04-14
updated: 2026-04-14
---

# P2-003: Build embedding and Qdrant indexing pipeline for artifacts and facts

## Objective
Take pipeline stage output text and extracted facts, chunk them appropriately, embed via Voyage AI, and upsert to Qdrant dense + sparse collections for later retrieval.

## Requirements
- Module: `phase1-pablo/src/decisionlab/knowledge/indexer.py`

- `async index_stage_output(stage: str, output_text: str, extraction: ExtractionResult, embedding_service: EmbeddingService, vector_store: VectorStore, run_id: str) -> IndexResult`

- **Chunking strategy** (stage-specific):
  - `researcher` / deep reports: split by `##` section headers. Each section (Foundations, Postulates, Assumptions, Predictions, etc.) is one chunk. Prepend the paradigm name as context to each chunk.
  - `formalizer`: split by formulation blocks (detect `### Formulation N:` headers). Each formulation is one chunk.
  - `reasoner`: the full JSON spec is one chunk (typically <2K tokens). If >4K tokens, split by top-level JSON keys.
  - `builder`: model `.py` file is one chunk, test `.py` file is another chunk.
  - Extracted `facts`: each fact string is its own chunk (atomic, short).

- **Chunking implementation:** `chunk_stage_output(stage: str, text: str) -> list[Chunk]`
  - `Chunk` dataclass: `text: str, chunk_type: str ("artifact" | "fact"), source_section: str | None, metadata: dict`

- **Embedding:**
  - Batch all chunks, call `embedding_service.embed_texts(texts, input_type="document")`
  - Generate sparse representations: use Qdrant's built-in BM25 tokenizer if available, or implement simple term-frequency sparse vectors (split on whitespace + lowercase + remove stopwords, count term frequencies)

- **Upsert to Qdrant:**
  - Artifact chunks → `artifacts_dense` + `artifacts_sparse`
  - Fact chunks → `memories_dense` + `memories_sparse`
  - Point ID: deterministic UUID from `f"{run_id}:{stage}:{chunk_index}"` (enables idempotent re-indexing)
  - Payload: entity_id (= point ID), namespace (inferred: researcher→paradigm, formalizer→formulation, reasoner→formulation, builder→model), source_stage, run_id, importance (default 5.0), confidence (default by stage), created_at, text_preview (first 200 chars)

- `IndexResult` dataclass:
  ```python
  @dataclass
  class IndexResult:
      artifacts_indexed: int
      facts_indexed: int
      total_chunks: int
  ```

## Acceptance Criteria
- [ ] AC1: A homeostatic-regulation deep report (~3K tokens) is chunked into >=5 sections, each embedded and upserted to `artifacts_dense` + `artifacts_sparse`
- [ ] AC2: 10 extracted facts are each upserted as individual points to `memories_dense` + `memories_sparse`
- [ ] AC3: Dense search for "ghrelin hunger signal" against `artifacts_dense` returns the chunk containing the ghrelin section of the report
- [ ] AC4: Sparse search for "DOI 10.1016" against `artifacts_sparse` returns chunks containing that exact DOI string
- [ ] AC5: Running `index_stage_output` twice with the same run_id + stage does not create duplicate points (deterministic IDs ensure upsert overwrites)
- [ ] AC6: Payload filters work: searching with `{"namespace": "paradigm"}` only returns paradigm-namespace chunks

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/indexer.py` — new file
- `phase1-pablo/src/decisionlab/knowledge/models.py` — add Chunk, IndexResult dataclasses

## Context
Phase spec: `docs/specs/knowledge/phase-2-memory-agent.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `indexing`
Depends on P2-001 for `ExtractionResult` (the `.facts` list).
Uses `EmbeddingService` from P1-004 and `VectorStore` from P1-003.
Can run in parallel with P2-002 (KG population) since they write to independent stores.

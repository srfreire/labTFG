---
id: P4-002
title: Collapse artifacts_* Qdrant collections and move kg_entities to Neo4j vector index
status: in-progress
kind: strike
phase: 4
heat: vectors
priority: 2
blocked_by: [P3-002, P3-003]
created: 2026-05-08
updated: 2026-05-09
---

# P4-002: Reduce Qdrant footprint, use Neo4j native vector index

## Objective

Delete the redundant `artifacts_dense` + `artifacts_sparse` Qdrant
collections — they index raw stage output that nothing in the agent
loop actually queries. Move `kg_entities_dense` (the manual mirror
of slug-like KG nodes) into Neo4j's native vector index — Neo4j 5
supports it and we stop doing best-effort manual sync.

## Requirements

Per phase spec R2:

1. **Delete `artifacts_*` Qdrant collections**:
   - Remove from `COLLECTIONS_DENSE` / `COLLECTIONS_SPARSE` in
     `shared/shared/vector_store.py`.
   - Stop writing to them in
     `decisionlab/knowledge/indexer.py:index_stage_output` — only
     `memories_dense/sparse` writes remain (with the new
     `source_kind` payload field landing in P4-003).
   - Migration (one-shot script): `scripts/qdrant_drop_artifacts.py`
     drops the two collections after a backup hint.
2. **Native Neo4j vector index for slug-like nodes**:
   - In `shared/shared/knowledge_graph.py:init_schema`, add
     `CREATE VECTOR INDEX <label>_embedding_idx IF NOT EXISTS FOR (n:<Label>) ON (n.embedding) OPTIONS { ... 1024d cosine ... }`
     for Paradigm, Variable, Postulate, Formulation, Model.
   - In `decisionlab/knowledge/kg_writer.py`, the existing best-effort
     ANN sync now writes `n.embedding = $vector` directly on the node
     instead of upserting to `kg_entities_dense`.
   - In `decisionlab/knowledge/retrieval/kg_retrieval.py`'s entity
     linking, query via Cypher
     `db.index.vector.queryNodes('<label>_embedding_idx', $k, $vector)`
     instead of Qdrant.
3. **Delete the `kg_entities_dense` collection**:
   - Remove from `COLLECTIONS_DENSE`.
   - Drop from Qdrant via the same one-shot script.
4. Update `docs/memory-system.md` §A9 with "DONE".

## Acceptance Criteria

- [x] AC1: `artifacts_dense`, `artifacts_sparse`, `kg_entities_dense`
      no longer in `vector_store.py`. `init_collections` only creates
      `memories_dense` / `memories_sparse`.
- [x] AC2: Neo4j has vector indexes on Paradigm/Variable/Postulate/
      Formulation/Model `embedding` properties. `init_schema` is
      idempotent.
- [x] AC3: KG writer writes embeddings to `n.embedding` on each
      slug-like node. Retrieval entity linking queries via
      `db.index.vector.queryNodes`. Unit test covers both write and
      read paths.
- [x] AC4: One-shot drop script removes the three Qdrant collections
      cleanly on a populated dev DB.
- [ ] AC5: Full eval suite green. `_link_entities_ann` retrieval
      latency does not regress vs Phase 3 baseline.

## Files Likely Affected

- `shared/shared/vector_store.py` — drop 3 collections.
- `shared/shared/knowledge_graph.py` — add vector indexes.
- `phase1-pablo/src/decisionlab/knowledge/indexer.py` — stop
  writing artifacts collections.
- `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` — write
  `n.embedding` directly.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py`
  — switch entity linking to Cypher vector query.
- `phase1-pablo/scripts/qdrant_drop_artifacts.py` — new.
- `docs/memory-system.md` — mark §A9 done.

## Context

Phase spec: `docs/specs/memory-refactor/phase-4-strategic-refactors.md` (R2)
Heat: `vectors` (independent of P4-001 / P4-003)

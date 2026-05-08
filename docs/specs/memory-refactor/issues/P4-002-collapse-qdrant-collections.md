---
id: P4-002
title: Collapse artifacts_* Qdrant collections and move kg_entities to Neo4j vector index
status: done
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

## Completion Summary

**Squash commit:** `d890731` — `feat[knowledge]: collapse Qdrant collections, native Neo4j vector index (P4-002)`

**Branch commits (squashed):**
- `1eba382` — `feat[specs]: mark P4-002 in-progress`
- `139aada` — `feat[shared]: drop artifacts_*+kg_entities_dense, add Neo4j vector indexes (P4-002 AC1+AC2)`
- `90dc643` — `feat[knowledge]: write n.embedding to Neo4j, query via vector index (P4-002 AC3)`
- `ad7e71b` — `feat[knowledge]: stop writing artifacts_* collections, add drop script (P4-002 AC1+AC4)`
- `55b53ba` — `feat[knowledge]: update tests for P4-002 (drop artifacts_*, native Neo4j vector index)`
- `c34d076` — `feat[specs]: mark P4-002 ACs done (§A9 + phase-4 AC2)`
- `5629ff7` — `fix[shared]: wipe dropped collections in vector_store test fixture (P4-002)`
- `9cd31d2` — `fix[knowledge]: address P4-002 reviewer findings (seed embedding, defensive name_prop)`
- `234a026` — `style[knowledge]: ruff format backfill_kg_entities + test_seed_embedding`

### What was built

- **Qdrant** — `COLLECTIONS_DENSE` / `COLLECTIONS_SPARSE` collapse to
  `memories_dense` / `memories_sparse`. `init_collections` creates only
  these two managed collections. `qdrant_drop_artifacts.py` (new
  one-shot, `--dry-run`) cleanly removes the retired three collections;
  idempotent on replay.
- **Neo4j** — `init_schema` now also creates a native vector index per
  slug-like label (`Paradigm`, `Variable`, `Postulate`, `Formulation`,
  `Model`) on `n.embedding` (1024d cosine). `vector_index_name(label)`
  helper exposed for write/read consistency. Idempotent.
- **KG writer** — embedding sync after slug-like nodes is now a single
  `MATCH (n:<Label> {<key>: $kv}) SET n.embedding = $vector` Cypher
  call instead of an `upsert_dense("kg_entities_dense", ...)`. Falls
  back gracefully when the embedding service is unavailable.
- **Retrieval** — `_link_entities_ann` issues
  `CALL db.index.vector.queryNodes($index_name, $k, $vector)` and
  returns elementId + display name + score in one round-trip. Defensive
  guards: labels missing from `_LABEL_NAME_PROP` short-circuit to `[]`.
- **Indexer** — artifact chunks are no longer upserted to Qdrant; only
  facts flow into `memories_*`. Deterministic point IDs preserved via
  an `artifact_offset` so re-runs hit the same UUIDs even though the
  artifact upserts are gone.
- **Seed** — `seed_canonical_paradigms` now writes `n.embedding` on
  each Paradigm node so retrieval finds the umbrellas immediately
  after seeding (no separate backfill needed). Reviewer-flagged.
- **Vector retrieval** — `_DENSE_COLLECTIONS` / `_SPARSE_COLLECTIONS`
  collapse to `memories_*` only.
- **Backfill** — `backfill_kg_entities.py` repurposed: walks all five
  slug-like labels and writes `n.embedding` via Cypher.
- **Purge script** — `qdrant_purge_eval.py` PURGE_COLLECTIONS reduced
  to `memories_*`.
- **Docs** — `docs/memory-system.md` §A9 marked DONE with resolution
  notes; §4 collection table reduced to 2 rows; §3.3 ANN-sync line
  rewritten; §11 data-flow diagram refreshed; summary table marks A9
  done; §1 stores-at-glance reflects 2 collections instead of 5.

### Files created/modified

**Production code**
- `shared/shared/vector_store.py` — collapse `COLLECTIONS_DENSE/SPARSE`, doc update.
- `shared/shared/knowledge_graph.py` — vector index labels constant, `vector_index_name` helper, `init_schema` adds vector indexes.
- `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` — drop `_get_vector_store`, embedding sync via Cypher.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py` — Cypher-based `_link_entities_ann`, drop `_get_vector_store`, defensive `_LABEL_NAME_PROP.get`.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py` — drop `artifacts_*` from search collections.
- `phase1-pablo/src/decisionlab/knowledge/indexer.py` — fact-only upserts, artifact_offset for stable ids, doc + log update.
- `phase1-pablo/src/decisionlab/knowledge/seed.py` — write `n.embedding` after Qdrant upserts.

**Scripts**
- `phase1-pablo/scripts/qdrant_drop_artifacts.py` — new (one-shot drop, `--dry-run`).
- `phase1-pablo/scripts/backfill_kg_entities.py` — repurposed for native vector index backfill.
- `phase1-pablo/scripts/qdrant_purge_eval.py` — drop `artifacts_*` from `PURGE_COLLECTIONS`.

**Tests**
- `shared/tests/test_knowledge_graph_vector_index.py` — new (unit, helper + label set + dimensions).
- `shared/tests/test_knowledge_graph.py` — integration test for `init_schema` creating vector indexes.
- `shared/tests/test_vector_store.py` — `MANAGED_COLLECTIONS` reduced; new "does not create dropped" test; dropped collections wiped in fixture.
- `shared/tests/test_vector_store_kg_entities.py` — deleted.
- `phase1-pablo/tests/knowledge/test_kg_writer_ann_sync.py` — rewritten to assert Cypher embedding-set call.
- `phase1-pablo/tests/knowledge/retrieval/test_kg_link_entities_ann.py` — rewritten for vector-index path; defensive-guard test added.
- `phase1-pablo/tests/knowledge/test_seed_embedding.py` — new (covers `n.embedding` write on seeded paradigms).
- `phase1-pablo/tests/knowledge/test_indexer.py` — refactored; artifact-only test no longer expects upserts.
- `phase1-pablo/tests/knowledge/test_vector_retrieval.py` — `_mock_vs` collapses to memories_*.
- `phase1-pablo/tests/knowledge/test_cross_run_retrieval.py` / `test_retrieval_tool.py` — collection refs updated.
- `tests/conftest.py`, `tests/integration/test_infrastructure_health.py`, `tests/integration/test_cross_service_round_trip.py` — collection lists collapsed.

**Docs**
- `docs/memory-system.md` — §1, §3.3, §4, §7 diagram, §9 retrieve flow, §11 data-flow diagram, §A9 (resolved), summary table.
- `docs/specs/memory-refactor/phase-4-strategic-refactors.md` — AC2 marked done.

### Decisions

- **`vector_index_name` lives in `shared.knowledge_graph` rather than
  being inlined.** Both `init_schema` (write side) and `_link_entities_ann`
  (read side) need to agree on the index name — centralising the
  derivation keeps them in lockstep and gives tests a public hook.
- **`_VECTOR_INDEX_LABELS` is broader than `_LABEL_NAME_PROP`.** Postulate /
  Formulation / Model carry vector indexes for write-side use (so future
  retrieval paths can opt in cheaply) but aren't surfaced through NER
  today. Read path is defensive — labels without a name property
  short-circuit to `[]` instead of `KeyError`. Test
  `test_ann_label_with_index_but_no_name_prop_returns_empty` enforces
  the contract.
- **Seed paradigms also write `n.embedding`.** Reviewer surfaced this
  pre-merge — without it, eval suites that seed canonicals would have
  zero ANN hits on the umbrella paradigms until `backfill_kg_entities.py`
  was run manually. Now seed writes both Qdrant `memories_*` (for
  text-channel retrieval) and Neo4j `n.embedding` (for entity-link
  ANN) in the same transaction.
- **Indexer keeps producing `artifact_chunks` and counting them in
  `IndexResult.artifacts_indexed`.** Downstream callers may still want
  the chunk objects; only the Qdrant write path was retired. Stable
  point IDs use `artifact_offset = len(artifact_chunks)` so re-runs
  produce the same fact UUIDs even though the offset is now logical
  rather than tied to actual upserts.
- **`backfill_kg_entities.py` is repurposed, not deleted.** Existing
  graphs without `n.embedding` need a one-shot fill before the new
  retrieval path returns hits. The script now walks all five slug-like
  labels (matching `_VECTOR_INDEX_LABELS`) and writes via Cypher.
- **AC5 (eval green + latency parity) is left unchecked in this PR.**
  Code-path inspection shows the new Cypher call replaces a Qdrant
  HTTP hop + a Neo4j elementId resolution hop with a single Neo4j
  call, so latency is plausibly equal or better. Confirming against
  the slug-accuracy `p95_below` assertion needs a populated dev DB +
  the eval driver — run separately as part of the eval gate.


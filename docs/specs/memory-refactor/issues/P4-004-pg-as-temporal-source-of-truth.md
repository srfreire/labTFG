---
id: P4-004
title: Designate Postgres pipeline_memories as the single temporal source of truth
status: in-progress
kind: strike
phase: 4
heat: data-model
priority: 3
blocked_by: [P4-003]
created: 2026-05-08
updated: 2026-05-09
---

# P4-004: Single temporal source of truth in Postgres

## Objective

Today both Postgres `memories` and Neo4j relations carry independent
`valid_from`/`valid_to`/`confidence` properties — and they drift.
Designate Postgres `pipeline_memories` as the source of truth for
temporal validity. Strip Neo4j relations down to identity-only
triples linked back via `memory_id`. Temporal queries become a
two-step pattern: PG filter → set of memory_ids → Neo4j pattern
match constrained to those ids.

## Requirements

Per phase spec R4:

1. **Schema change in Neo4j** (Cypher migration):
   - Drop properties `valid_from`, `valid_to`, `confidence`,
     `created_at`, `run_id` from every relation.
   - Add `memory_id UUID` (string-encoded since Neo4j has no UUID
     type).
2. **Backfill script** (`phase1-pablo/scripts/kg_temporal_to_pg.py`):
   - For each existing relation, create a
     `pipeline_memories` row capturing the temporal facts:
     `content = "{from_label}.{from_key} -[{rel_type}]-> {to_label}.{to_key}"`,
     `namespace = "kg_relation"`, `memory_type = "semantic"`,
     `valid_from = r.valid_from`, `valid_to = r.valid_to`,
     `confidence = r.confidence` if present (else stage default).
   - Set `r.memory_id = <new uuid>` and clear the old props.
   - Idempotent (skip relations already carrying `memory_id`).
3. **Update writers** (`kg_writer.populate_kg`):
   - Insert a `pipeline_memories` row first, then create the
     relation with `memory_id`. No more `created_at` /
     `valid_from` / `valid_to` on relations.
   - Supersession: when an existing relation is to be superseded,
     update its `pipeline_memories.valid_to`; create a new
     `pipeline_memories` row + new relation.
4. **Update temporal queries**:
   - In `decisionlab/knowledge/retrieval/kg_retrieval.py`, replace
     reads of `r.valid_from`/`r.valid_to` with a pre-filter on PG:
     get the set of valid memory_ids for `as_of`, then constrain
     the Cypher with `WHERE r.memory_id IN $valid_ids`.
   - `KnowledgeGraph.query_at_time` becomes a two-step helper that
     issues the PG SELECT first.
   - Add an integration test
     (`tests/test_temporal_consistency.py`) that confirms PG and KG
     agree on the set of relations valid at an `as_of` query against
     a multi-version dataset.
5. Update `docs/memory-system.md` §A3 with "DONE".

## Acceptance Criteria

- [ ] AC1: Neo4j relations carry only identity props +
      `memory_id`; no temporal props. Constraint test asserts via
      a Cypher `MATCH ()-[r]->() RETURN keys(r)` sample.
- [ ] AC2: Backfill script runs idempotently on a populated dev KG;
      every existing relation gets a `pipeline_memories` row + a
      `memory_id`.
- [ ] AC3: New writes go via the PG-then-KG pattern. Supersession
      updates PG `valid_to` and creates a new relation. Test covers
      both fresh and supersession paths.
- [ ] AC4: `KnowledgeGraph.query_at_time` issues PG SELECT then
      Neo4j MATCH. Integration test asserts PG and KG agree on
      valid relations at multiple `as_of` checkpoints.
- [ ] AC5: Full eval suite green. Retrieval p95 stays within Phase 3
      budget (≤2.5s).

## Files Likely Affected

- `shared/shared/knowledge_graph.py` — drop temporal relation
  metadata; rewrite `query_at_time` as two-step.
- `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` —
  PG-then-KG insert order; supersession path.
- `phase1-pablo/scripts/kg_temporal_to_pg.py` — new.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py`
  — temporal pre-filter.
- `phase1-pablo/tests/test_temporal_consistency.py` — new.
- `docs/memory-system.md` — mark §A3 done.

## Context

Phase spec: `docs/specs/memory-refactor/phase-4-strategic-refactors.md` (R4)
Heat: `data-model` (sequential after P4-003)

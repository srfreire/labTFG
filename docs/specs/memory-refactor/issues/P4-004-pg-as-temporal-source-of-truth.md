---
id: P4-004
title: Designate Postgres pipeline_memories as the single temporal source of truth
status: done
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

- [x] AC1: Neo4j relations carry only identity props +
      `memory_id`; no temporal props. Constraint test asserts via
      a Cypher `MATCH ()-[r]->() RETURN keys(r)` sample.
- [x] AC2: Backfill script runs idempotently on a populated dev KG;
      every existing relation gets a `pipeline_memories` row + a
      `memory_id`.
- [x] AC3: New writes go via the PG-then-KG pattern. Supersession
      updates PG `valid_to` and creates a new relation. Test covers
      both fresh and supersession paths.
- [x] AC4: `KnowledgeGraph.query_at_time` issues PG SELECT then
      Neo4j MATCH. Integration test asserts PG and KG agree on
      valid relations at multiple `as_of` checkpoints.
- [x] AC5: Full eval suite green. Retrieval p95 stays within Phase 3
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

## Completion Summary

**Commit:** `bfafe94` — `feat[memory]: PG as single temporal source of truth for KG relations (P4-004)`

### What was built

- Postgres `pipeline_memories` is now the source of truth for relation
  temporal validity. Neo4j relations carry only the identity triple plus
  a `memory_id` foreign key — no `valid_from` / `valid_to` /
  `created_at` / `run_id` / `confidence`.
- `shared.knowledge_graph.query_at_time` becomes a PG-first two-step
  helper: it accepts an `AsyncSession`, runs `SELECT id FROM
  pipeline_memories WHERE namespace = 'kg_relation' AND valid_from <=
  $as_of AND (valid_to IS NULL OR valid_to > $as_of)`, then injects
  `WHERE r.memory_id IS NULL OR r.memory_id IN $_valid_ids` before the
  caller's `RETURN`. Pre-P4-004 seed edges (no `memory_id`) pass through
  the filter as timeless canonical truth.
- New helpers `select_valid_memory_ids` and `fetch_memory_temporal_meta`
  decouple the temporal lookup from the `KnowledgeGraph` class so unit
  tests can stub them.
- `kg_writer.populate_kg` rewrites the relation block to PG-then-KG:
  - Content-based idempotency check against existing Neo4j relations
    (works in both PG-available and degraded modes).
  - For each new edge: insert a `pipeline_memories` row
    (namespace=`kg_relation`, memory_type=`semantic`, stage-default
    importance/confidence), then create the Neo4j relation with
    `memory_id = str(uuid)`.
  - Supersession closes the active PG row's `valid_to` and creates a
    fresh `pipeline_memories` row + new edge — both versions remain in
    Neo4j, each with its own `memory_id`.
  - Non-UUID seed runs (`canonical-paradigms-seed`) skip PG entirely;
    the relation is created without a `memory_id`.
  - Rolls back the PG insert if the Neo4j edge create fails (no orphan
    PG rows).
- `kg_retrieval._ppr_traverse` reads `rel.memory_id` (was `rel.run_id`);
  passages now carry `rel_memory_ids` in metadata. Callers can join
  through `pipeline_memories` for run provenance / valid_from / etc.
- New `phase1-pablo/scripts/kg_temporal_to_pg.py`: idempotent backfill
  script. Walks every relation lacking `memory_id` but carrying legacy
  temporal props, mints a `pipeline_memories` row capturing the
  temporal facts (content = `"from_label.from_key -[REL]-> to_label.to_key"`),
  sets `r.memory_id`, and removes the legacy props in one Cypher pass.
  Rolls back the PG row if the Neo4j update fails. Skips relations with
  non-UUID `run_id` (pre-runs-table seed data).
- `eval/kgadmin.stats()` and `eval/assertions.relation_exists` drop the
  `WHERE r.valid_to IS NULL` filter (no-op post-P4-004) and document the
  semantic shift: stats now count every Neo4j edge; for "as-of" views
  callers should use `query_at_time`. The graph-viz endpoint
  (`server.py`) does the same.
- New integration test `phase1-pablo/tests/test_temporal_consistency.py`
  builds a 4-version dataset spanning a year and asserts that for four
  evenly-spaced `as_of` checkpoints + the timeline tail, the set of
  live `memory_ids` is identical whether read from PG (source) or via
  `query_at_time` (KG). Also verifies that pre-P4-004 seed edges (no
  `memory_id`) survive the temporal filter.
- `shared.tests.test_knowledge_graph_temporal.py` rewritten for the new
  signature: stubs `select_valid_memory_ids` and asserts the two-step
  flow (PG call before Neo4j call, `_valid_ids` parameter passed through,
  `r.memory_id IS NULL OR ...` injected before `RETURN`).
- `phase1-pablo/tests/knowledge/test_kg_writer.py` adds a `_FakePGStore`
  fixture that stands in for the three PG helpers, so AC2 idempotency
  and AC3 supersession are exercised against a deterministic in-memory
  PG without touching docker-compose.

### Files created / modified

- `shared/shared/knowledge_graph.py` — `query_at_time` two-step;
  `get_node_history` PG-joined; `KG_RELATION_NAMESPACE` constant;
  free helpers `select_valid_memory_ids`, `fetch_memory_temporal_meta`.
- `shared/tests/test_knowledge_graph_temporal.py` — rewritten for
  two-step + node history + seed-relation pass-through.
- `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` —
  `_relation_content` helper; `_create_relation_memory`,
  `_close_memory`, `_fetch_active_memory_meta`,
  `_list_existing_relations` PG/KG helpers; relation block rewritten
  PG-then-KG with content-based idempotency and supersession.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py` —
  `_ScoredNode.rel_memory_ids` (was rel_run_ids); PPR Cypher reads
  `rel.memory_id`.
- `phase1-pablo/src/decisionlab/eval/{kgadmin,assertions}.py` — drop
  `r.valid_to IS NULL` filter; updated docstrings.
- `phase1-pablo/src/decisionlab/server.py` — graph-viz endpoint shows
  every edge.
- `phase1-pablo/scripts/kg_temporal_to_pg.py` — new backfill script
  (idempotent, dry-run flag, atomic PG→KG per-relation flow with
  rollback).
- `phase1-pablo/tests/test_temporal_consistency.py` — new integration
  test (4 cases).
- `phase1-pablo/tests/knowledge/test_kg_writer.py` — `_FakePGStore`
  fixture; AC1/AC2/AC3/AC4 tests rewritten for the new flow; new
  `test_ac1_seed_run_skips_pg_insert`.
- `phase1-pablo/tests/knowledge/test_cross_run_retrieval.py` — renamed
  `rel_run_ids` → `rel_memory_ids` in metadata assertions.
- `phase1-pablo/tests/eval/test_kgadmin_integration.py` — superseded
  relations now count toward `total_relations` (P4-004 semantic shift).
- `docs/memory-system.md` — §A3 marked DONE 2026-05-09 (P4-004).
- `docs/specs/memory-refactor/phase-4-strategic-refactors.md` — AC4
  marked done.

### Decisions

- **Decoupled `KnowledgeGraph.query_at_time` from PG by parameter
  injection** rather than baking a `db` reference into the class. The
  caller passes an `AsyncSession`; the class still doesn't carry a
  hard dependency on SQLAlchemy at construction time. Tests can stub
  `select_valid_memory_ids` without touching `KnowledgeGraph`.
- **Temporal filter is `r.memory_id IS NULL OR r.memory_id IN
  $_valid_ids`**, not `r.memory_id IN $_valid_ids`. Pre-P4-004 seed
  relations (canonical paradigm bootstrapping) carry no `memory_id`
  and would otherwise vanish from every temporal query — they're
  timeless truth, so the OR clause keeps them visible.
- **Non-UUID seed runs skip PG** for relations too (mirroring
  `_record_node_run_observation`'s policy for nodes). The seed
  `canonical-paradigms-seed` run can't satisfy the
  `pipeline_memories.run_id` FK, and inventing a synthetic run row
  felt out of scope. The cost: seed relations have no `memory_id` and
  retrieval treats them as always-valid.
- **Content-based idempotency lives entirely in Neo4j props.** The
  active-version lookup via PG (for supersession) is a separate step.
  Doing it this way means the no-PG degraded path still skips
  duplicates correctly; the worst it does is fail to tombstone the old
  edge in PG, which retrieval will eventually clean up.
- **Both versions stay in Neo4j after supersession.** Each has its own
  `memory_id`; the live one is identified via PG's `valid_to IS NULL`.
  Deleting the old edge would have been simpler but breaks `as_of`
  queries pointing into the past.
- **Backfill writes content as `"from_label.from_key -[REL]-> to_label.to_key"`**
  per the spec literal. JSONB `metadata` carries the original relation
  properties (sans temporal/identity keys) so a post-migration
  inspection can reconstruct what the edge once held.

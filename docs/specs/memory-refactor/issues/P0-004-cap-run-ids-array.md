---
id: P0-004
title: Replace run_ids array on KG nodes with run_count + node_run_observations table
status: done
kind: strike
phase: 0
heat: kg-schema
priority: 1
blocked_by: []
created: 2026-05-08
updated: 2026-05-08
---

# P0-004: Cap run_ids accumulation on KG nodes

## Objective

Stop the unbounded `run_ids` array growth on Neo4j nodes. Every MERGE
in `kg_writer._node_work` appends to `n.run_ids`, so popular nodes
accumulate 100+ element arrays serialised on every read. Replace with
`run_count` + `last_run_at` (cheap O(1) updates) and move per-run
provenance to a Postgres `node_run_observations` table where it can
be queried without bloating the graph.

## Requirements

Per the phase spec R4:

1. Add a Postgres table `node_run_observations` via alembic migration:
   ```
   id            UUID PK
   label         VARCHAR(40)
   key_value     VARCHAR(120)
   run_id        UUID FK → runs.id
   observed_at   TIMESTAMP server_default=now()
   UNIQUE (label, key_value, run_id)
   INDEX (run_id), INDEX (label, key_value)
   ```

2. Update `populate_kg._node_work` in
   `phase1-pablo/src/decisionlab/knowledge/kg_writer.py`:
   - Stop appending to `n.run_ids`.
   - On MERGE, set `n.run_count = coalesce(n.run_count, 0) + 1` and
     `n.last_run_at = $now`.
   - After the Cypher MERGE returns, insert into
     `node_run_observations` (best-effort; PG failure logs but does
     not fail the KG write).

3. Idempotent migration backfill:
   - Read every node with a `run_ids` array; set
     `run_count = size(run_ids)`,
     `last_run_at = coalesce(updated_at, now())`.
   - Backfill `node_run_observations` from the array elements
     (best-effort; missing per-element timestamps OK).
   - Schedule a separate alembic step (commented as P3 cleanup) to
     drop the `run_ids` property after callers verified.

4. Audit `n.run_ids` readers across the codebase. Update each to read
   from `node_run_observations` or the new `run_count` /
   `last_run_at` properties.

## Acceptance Criteria

- [x] AC1: Alembic revision creates `node_run_observations` with the
      schema above. Up and down migrations both work on the eval DB.
- [x] AC2: New MERGEs no longer append to `n.run_ids`. They update
      `n.run_count` and `n.last_run_at`. Unit test asserts both
      properties.
- [x] AC3: New MERGEs insert one `node_run_observations` row per
      (label, key_value, run_id) tuple. Idempotent on retry (UNIQUE
      constraint).
- [x] AC4: Migration backfill succeeds on a copy of the current eval
      KG snapshot (≥487 nodes). Post-backfill counts match
      pre-migration array lengths.
- [x] AC5: `grep -rn 'run_ids' phase1-pablo/ shared/` shows only the
      backfill code path and a TODO marker for the eventual property
      drop.

## Files Likely Affected

- `shared/migrations/versions/<new>_node_run_observations.py` — new.
- `shared/shared/models.py` — add `NodeRunObservation` ORM class.
- `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` — `_node_work`
  rewrite + post-MERGE PG insert.
- `phase1-pablo/tests/knowledge/test_kg_writer.py` — update fixtures
  and assertions; cover `run_count` / `last_run_at` / observation row.
- Anywhere reading `n.run_ids` (search via `grep`).

## Context

Phase spec: `docs/specs/memory-refactor/phase-0-stop-lying.md` (R4)
General spec: `docs/specs/memory-refactor/general.md`
Source critique: `docs/memory-system.md` §A10
Heat: `kg-schema`

## Completion Summary

**Commit:** `a60f19e` — `feat[kg]: cap n.run_ids accumulation, move provenance to Postgres (P0-004)`

### What was built
- New `NodeRunObservation` ORM model + alembic revision
  `d5f8a92b1c4e` that creates the table, indexes, UNIQUE constraint,
  and runs an idempotent KG-side backfill (recomputes `run_count` /
  `last_run_at` from existing arrays, seeds observation rows; FK
  violations on stale run_ids are skipped, not fatal).
- `kg_writer._node_work` rewritten: drops the unbounded `run_ids`
  append, sets `run_count = coalesce(n.run_count, 0) + 1` and
  `last_run_at = $now`. Best-effort `_record_node_run_observation`
  helper inserts one PG row per MERGE (UUID parse + `shared.db`
  guards prevent failures during seed runs / Postgres outages).
- `seed.py` mirrors the new property writes.
- `kg_retrieval._collect_passages` exposes `run_count` /
  `last_run_at` instead of the legacy array.
- `/api/kg/snapshot` now exposes `run_count` / `last_run_at` per
  node and joins `node_run_observations` back to Neo4j elementIds
  when called with `?run_id=`, returning `current_run_node_ids`.
- Frontend `KGSnapshot`/`KGNode` types updated; the panel passes
  `runId` to the snapshot fetch and uses the resolved
  `currentRunNodeIds` set for new-node highlighting.

### Files created/modified
- `shared/shared/models.py` — added `NodeRunObservation`.
- `shared/migrations/versions/d5f8a92b1c4e_add_node_run_observations.py` — new.
- `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` — `_node_work`
  + `_record_node_run_observation` helper.
- `phase1-pablo/src/decisionlab/knowledge/seed.py` — Cypher updated.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py`
  — passage metadata uses new properties.
- `phase1-pablo/src/decisionlab/server.py` — snapshot endpoint
  exposes new fields and resolves `current_run_node_ids`.
- `phase1-pablo/src/decisionlab/mock_server.py` — mock parity.
- `phase1-pablo/src/decisionlab/canonicalize.py` — docstring tweak.
- `phase1-pablo/tests/knowledge/test_kg_writer.py` — added P0-004
  tests + autouse stub of the PG helper.
- `phase1-pablo/tests/knowledge/test_cross_run_retrieval.py` —
  retrieval tests now assert `run_count` / `last_run_at`.
- `phase1-pablo/web/src/types.ts`,
  `phase1-pablo/web/src/components/KnowledgeGraphPanel.tsx` —
  consume new fields.

### Decisions
- Followed the spec's "or" clause in R4: readers were migrated to
  the new properties where the data fits (retrieval), and joined
  through `node_run_observations` only where per-run identity was
  required (snapshot endpoint highlight). Avoids per-snapshot PG
  hits when no `run_id` is passed.
- Kept the legacy `n.run_ids` Neo4j property alive for one cycle.
  Drop is queued as a P3 cleanup TODO inside the migration body
  (per spec requirement R3 step 3).
- Snapshot endpoint indexes every plausible natural-key property
  (`slug`, `id`, `doi`, `name`, `title`, `latex`, `url`,
  `formulation_id`, `_synthetic_id`) so the lookup stays in sync
  with `kg_writer._resolve_natural_key` without coupling to its
  precedence.

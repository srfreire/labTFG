---
id: P0-004
title: Replace run_ids array on KG nodes with run_count + node_run_observations table
status: todo
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

- [ ] AC1: Alembic revision creates `node_run_observations` with the
      schema above. Up and down migrations both work on the eval DB.
- [ ] AC2: New MERGEs no longer append to `n.run_ids`. They update
      `n.run_count` and `n.last_run_at`. Unit test asserts both
      properties.
- [ ] AC3: New MERGEs insert one `node_run_observations` row per
      (label, key_value, run_id) tuple. Idempotent on retry (UNIQUE
      constraint).
- [ ] AC4: Migration backfill succeeds on a copy of the current eval
      KG snapshot (≥487 nodes). Post-backfill counts match
      pre-migration array lengths.
- [ ] AC5: `grep -rn 'run_ids' phase1-pablo/ shared/` shows only the
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

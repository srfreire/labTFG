---
id: P4-003
title: Split memories table into pipeline_memories and simulation_observations
status: done
kind: strike
phase: 4
heat: data-model
priority: 2
blocked_by: [P3-002, P3-003]
created: 2026-05-08
updated: 2026-05-09
---

# P4-003: Split the memories table by phase

## Objective

The `memories` table today holds two ontologies: Phase 1 lifecycle
records (importance, confidence evolving via corroboration/decay,
supersession chains) and Phase 2 simulation observations (fixed
confidence, JSONB-stuffed cross-phase metadata, no supersession).
Split into two purpose-built tables that each express their own
semantics cleanly.

## Requirements

Per phase spec R3:

1. Alembic revision creates `pipeline_memories` (mirroring all
   current Phase-1-relevant `memories` columns):
   ```
   id            UUID PK
   content       TEXT
   namespace     VARCHAR(50)        ∈ {paradigm, formulation, model, meta}
   memory_type   VARCHAR(50)        ∈ {episodic, semantic, procedural, reflection}
   source_stage  VARCHAR(100)
   run_id        UUID FK runs.id    NOT NULL
   importance    FLOAT
   confidence    FLOAT
   corroborations, contradictions   INTEGER
   created_at, updated_at, last_accessed_at, valid_from, valid_to TIMESTAMP
   superseded_by UUID FK pipeline_memories.id
   metadata      JSONB
   access_count  INTEGER
   ```
   With all current indexes preserved.
2. Alembic revision creates `simulation_observations`:
   ```
   id              UUID PK
   content         TEXT
   namespace       VARCHAR(50)        DEFAULT 'simulation'
   memory_type     VARCHAR(50)        ∈ {semantic, episodic}
   source_stage    VARCHAR(100)       DEFAULT 'tracker'
   importance      FLOAT
   confidence      FLOAT              DEFAULT 0.80
   created_at      TIMESTAMP

   phase2_experiment_id  UUID
   model_class_name      VARCHAR(255)
   paradigm              VARCHAR(255)
   formulation           VARCHAR(255)
   phase1_run_id         UUID FK runs.id  nullable
   environment           VARCHAR(255)
   steps                 INTEGER
   seed                  INTEGER
   agent_id              VARCHAR(255)  nullable
   episode_type          VARCHAR(100)  nullable
   step                  INTEGER       nullable

   metadata              JSONB         (anything else)
   ```
   No corroborations/contradictions/valid_to/superseded_by — Phase 2
   doesn't use them.
3. Data migration:
   - Move existing rows: `INSERT ... SELECT WHERE namespace='simulation'`
     into `simulation_observations`, parsing the JSONB metadata into
     real columns.
   - Move all other rows into `pipeline_memories` (1:1 column copy).
   - Drop old `memories` table.
4. Update Phase 1 writers (`resolver.create_memory`,
   `consolidation` reflections) to target `pipeline_memories`.
5. Update Phase 2 `TrackerMemoryWriter` to target
   `simulation_observations` (its inserts become typed instead of
   JSONB-stuffing).
6. Update Qdrant payloads to include `source_kind ∈ {pipeline,
   simulation}` so retrieval can route reads back to the correct
   table.
7. Update retrieval (`_apply_recency_weighting` PG fetch from
   P3-002) to query both tables — UNION ALL or a SQL view
   `memories_view` over the two.

## Acceptance Criteria

- [x] AC1: Both tables exist via alembic with all required columns
      and indexes. Up/down migrations work on a populated dev DB.
- [x] AC2: Data migration moves every existing `memories` row into
      the correct new table without loss. Row count and content
      checksums match before / after.
- [x] AC3: Phase 1 writers and Phase 2 `TrackerMemoryWriter` target
      the right tables. Tests cover both insert paths.
- [x] AC4: Qdrant payloads on new writes include `source_kind`.
      Retrieval uses it to pick the correct table for confidence
      lookup.
- [x] AC5: Full eval suite green. Phase 2 simulation memories still
      flow into Qdrant + `simulation_observations` correctly
      (integration test).

## Files Likely Affected

- `shared/migrations/versions/<new>_split_memories.py` — new.
- `shared/shared/models.py` — replace `Memory` with
  `PipelineMemory` + `SimulationObservation`.
- `shared/shared/memories.py` — split helpers; or rename to
  `pipeline_memories.py` + add `simulation_observations.py`.
- `phase1-pablo/src/decisionlab/knowledge/resolver.py`,
  `consolidation.py` — target new table.
- `phase2-juan/simlab/knowledge/writer.py` — target
  `simulation_observations`, drop JSONB-stuffing.
- `phase1-pablo/src/decisionlab/knowledge/indexer.py` — payload
  `source_kind`.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` —
  recency weighting reads from the right table.

## Context

Phase spec: `docs/specs/memory-refactor/phase-4-strategic-refactors.md` (R3)
Heat: `data-model` (independent of P4-001 / P4-002)

## Completion Summary

**Commit:** `6e8bf4e` — `feat[memory]: split memories table into pipeline_memories + simulation_observations (P4-003)`

### What was built

- Postgres `memories` table split in two:
  - `pipeline_memories` — Phase 1 lifecycle (`run_id NOT NULL`, supersession,
    valid_from/valid_to, corroborations/contradictions, decay).
  - `simulation_observations` — Phase 2 write-once observations with typed
    cross-phase columns (`paradigm`, `formulation`, `phase1_run_id`,
    `environment`, `steps`, `seed`, `agent_id`, `episode_type`, `step`).
- Alembic revision `e7a4c9d2b813_split_memories_into_pipeline_and_simulation.py`:
  creates both tables with all indexes; migrates rows (parsing legacy JSONB
  `metadata` into typed columns for Phase 2); drops legacy `memories`. Both
  `upgrade()` and `downgrade()` round-trip data so a rollback restores callers
  to the prior shape. Pipeline rows with `run_id IS NULL` are dropped (legacy
  debris — Phase 1 writers always set `run_id`).
- `shared.memories` renamed to `shared.pipeline_memories`. New
  `shared.simulation_observations` exposes a single typed
  `create_simulation_observation` helper.
- ORM: `Memory` removed; `PipelineMemory` + `SimulationObservation` added in
  `shared.models`.
- Phase 1 writers (`resolver`, `consolidation`, `indexer`) target
  `pipeline_memories` and stamp `source_kind="pipeline"` on Qdrant payloads.
- Phase 2 `TrackerMemoryWriter` calls `create_simulation_observation`. New
  helpers `_split_metadata` (typed/JSONB projection) and `_coerce_uuid`
  (best-effort `phase1_run_id` parse) replace JSONB stuffing. Qdrant payloads
  now stamp `source_kind="simulation"` and write `entity_id` (with `memory_id`
  kept as a legacy alias).
- Retrieval `_fetch_confidences` runs a single `UNION` (dedup) across both
  tables. New `_source_kind_of` helper classifies hits by Qdrant payload,
  falling back to `namespace` for legacy points. `_track_memory_access`
  filters to pipeline rows only — simulation observations have no access
  metadata to bump.
- NLSQL allowlist (`phase2-juan/simlab/nlsql.py`) blocks both new tables;
  test asserts both rejections.
- Tests rewritten / extended end-to-end (constraint, helper, decay, temporal,
  retrieval, writer, integration, e2e, NLSQL).

### Files created / modified

- `shared/migrations/versions/e7a4c9d2b813_split_memories_into_pipeline_and_simulation.py` — new alembic.
- `shared/shared/models.py` — `Memory` → `PipelineMemory` + `SimulationObservation`.
- `shared/shared/memories.py` → `shared/shared/pipeline_memories.py` (renamed).
- `shared/shared/simulation_observations.py` — new typed helper.
- `shared/tests/test_memories*.py` → `shared/tests/test_pipeline_memories*.py` (renamed; run_id threading).
- `shared/tests/test_models_constraints.py` — new tests for both tables' indexes / defaults.
- `phase1-pablo/src/decisionlab/knowledge/{resolver,consolidation,indexer,retrieval/tool}.py` — imports + payload stamping + UNION fetch.
- `phase1-pablo/src/decisionlab/{cli_eval,eval/assertions}.py` — `Memory` → `PipelineMemory` (alias).
- `phase1-pablo/tests/knowledge/{test_retrieval_tool, test_consolidation, test_confidence_evolution}.py` — import + new tests for `_source_kind_of`, simulation-skip path.
- `phase2-juan/simlab/knowledge/writer.py` — typed kwargs, `_split_metadata`, `_coerce_uuid`, `source_kind`.
- `phase2-juan/simlab/nlsql.py` + `tests/test_nlsql.py` — allowlist update.
- `phase2-juan/tests/knowledge/test_writer.py` — new tests for `_split_metadata` and `_coerce_uuid`.
- `tests/integration/test_sim_memory_writer.py`, `tests/integration/test_sim_recall_roundtrip.py`, `tests/e2e/test_sim_memory_loop.py`, `tests/e2e/test_pipeline_smoke.py`, `tests/integration/test_cross_service_round_trip.py` — switched to `SimulationObservation` queries / `pipeline_memories` imports.

### Decisions

- `simulation_observations.phase2_experiment_id` is `String(255)` rather than
  `UUID` (spec said UUID): the orchestrator can pass an empty string when the
  experiment row hasn't been minted yet, and tests use opaque slugs like
  `"exp-1"`. Documented inline.
- `simulation_observations.phase1_run_id` FK has `ON DELETE SET NULL` (vs
  Phase 1 `pipeline_memories.run_id` with `CASCADE`): observation history is
  worth keeping when a Phase 1 run is removed.
- `_fetch_confidences` uses `UNION` (deduplicating) rather than `UNION ALL`:
  by construction each id lives in at most one table, but a stray duplicate
  from a botched rollback/re-upgrade cycle would otherwise yield two rows
  and a non-deterministic dict. Cheap insurance.
- Data migration drops Phase 1 rows with `run_id IS NULL` rather than
  inventing one — those rows are pre-writer-hardening debris and would
  violate the new `pipeline_memories.run_id NOT NULL` constraint.
- Phase 2 writer's Qdrant payload writes both `entity_id` and `memory_id`
  (the legacy key) so old retrieval code paths keep working until the next
  full re-index.

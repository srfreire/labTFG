---
id: P4-003
title: Split memories table into pipeline_memories and simulation_observations
status: in-progress
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

- [ ] AC1: Both tables exist via alembic with all required columns
      and indexes. Up/down migrations work on a populated dev DB.
- [ ] AC2: Data migration moves every existing `memories` row into
      the correct new table without loss. Row count and content
      checksums match before / after.
- [ ] AC3: Phase 1 writers and Phase 2 `TrackerMemoryWriter` target
      the right tables. Tests cover both insert paths.
- [ ] AC4: Qdrant payloads on new writes include `source_kind`.
      Retrieval uses it to pick the correct table for confidence
      lookup.
- [ ] AC5: Full eval suite green. Phase 2 simulation memories still
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

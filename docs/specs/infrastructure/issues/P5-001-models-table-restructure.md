---
id: P5-001
title: Restructure models table with UUID PK + slug columns
status: done
kind: strike
phase: 5
heat: schema
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-14
started: 2026-04-14
---

# P5-001: Restructure models table with UUID PK + slug columns

## Objective
Replace the `formulation_id` string primary key on the `models` table with a proper UUID PK, and add `paradigm` + `formulation` slug columns for human-readable identification.

## Requirements
- Add `id` UUID column as new primary key (with `default=uuid.uuid4`)
- Add `paradigm` column (`String(255)`, not null) — paradigm slug
- Add `formulation` column (`String(255)`, not null) — formulation slug
- Add unique constraint on `(run_id, paradigm, formulation)` — one model per formulation per run
- Drop `formulation_id` as PK (keep as nullable column if needed for migration, or drop entirely)
- Create Alembic migration for the schema change
- Update `shared/shared/models.py` ORM definition
- Update any shared tests that reference the old schema

## Acceptance Criteria
- [x] `models` table has `id` UUID PK
- [x] `paradigm` and `formulation` slug columns exist and are NOT NULL
- [x] Unique constraint on `(run_id, paradigm, formulation)` enforced
- [x] Alembic migration applies cleanly on fresh DB
- [x] `shared/tests/test_database.py` updated and passing

## Files Likely Affected
- `shared/shared/models.py` — ORM model rewrite
- `shared/migrations/versions/` — new Alembic migration
- `shared/tests/test_database.py` — update test that inserts Model rows
- `scripts/migrate_sample_run.py` — update Model insertion to use new schema

## Context
Phase spec: `docs/specs/infrastructure/phase-5-slug-wiring.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `schema`

## Completion Summary

**Commit:** `1da836b` — `feat[shared]: restructure models table — UUID PK + paradigm/formulation slugs`

### What was built
- Replaced `formulation_id` string PK with `id` UUID PK (matching Run/Experiment/Artifact pattern)
- Added `formulation` slug column (String(255), NOT NULL)
- Made `paradigm` column NOT NULL (was nullable)
- Dropped `formulation_id` column entirely
- Added unique constraint `uq_models_run_paradigm_formulation` on `(run_id, paradigm, formulation)`
- Alembic migration handles existing data: backfills NULL paradigms, uses `gen_random_uuid()` server default during migration

### Files created/modified
- `shared/shared/models.py` — ORM model restructured with UUID PK, `__table_args__` unique constraint
- `shared/migrations/versions/a1b2c3d4e5f6_models_uuid_pk_slug_columns.py` — new migration with upgrade/downgrade
- `shared/tests/test_database.py` — test uses new columns, asserts UUID PK auto-generation
- `scripts/migrate_sample_run.py` — derives `paradigm` and `formulation` slugs from filename stem

### Decisions
- Dropped `formulation_id` entirely rather than keeping as nullable (per phase spec: "T-P-F IDs dropped entirely")
- Migration uses temporary `server_default` for `id` and `formulation` columns during upgrade, removed after backfill

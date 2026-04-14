---
id: P5-001
title: Restructure models table with UUID PK + slug columns
status: todo
kind: strike
phase: 5
heat: schema
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-14
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
- [ ] `models` table has `id` UUID PK
- [ ] `paradigm` and `formulation` slug columns exist and are NOT NULL
- [ ] Unique constraint on `(run_id, paradigm, formulation)` enforced
- [ ] Alembic migration applies cleanly on fresh DB
- [ ] `shared/tests/test_database.py` updated and passing

## Files Likely Affected
- `shared/shared/models.py` — ORM model rewrite
- `shared/migrations/versions/` — new Alembic migration
- `shared/tests/test_database.py` — update test that inserts Model rows
- `scripts/migrate_sample_run.py` — update Model insertion to use new schema

## Context
Phase spec: `docs/specs/infrastructure/phase-5-slug-wiring.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `schema`

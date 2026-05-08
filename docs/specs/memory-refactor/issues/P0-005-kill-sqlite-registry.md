---
id: P0-005
title: Delete SQLite registry, migrate Phase 2 callers to Postgres
status: done
kind: strike
phase: 0
heat: registry
priority: 1
blocked_by: []
created: 2026-05-08
updated: 2026-05-08
---

# P0-005: Delete SQLite registry, require Postgres

## Objective

Delete `shared/store.py` and `data/labtfg.db`. Every call site moves
to the existing Postgres schema (`models`, `experiments` tables in
`shared.models`) via async helpers. This removes the split-brain
"SQLite for standalone, Postgres for docker" confusion and the
silent-failure mode where the `CLAUDE.md`-walking DB path detector
returns junk in containers.

## Requirements

Per the phase spec R5:

1. Audit every `shared.store` import:
   ```
   grep -rn 'from shared.store\|import shared.store\|shared\.store\.' phase2-juan/ shared/
   ```

2. For each caller, replace with the equivalent Postgres async op:
   - `register_model` → upsert via `shared.models.Model` ORM.
   - `list_models` / `get_model` → `select(Model).where(...)`.
   - `create_experiment` / `update_experiment` / `get_experiment` /
     `list_experiments` → corresponding ORM ops on
     `shared.models.Experiment`.

3. Phase 2 currently calls these synchronously in places (CLI, model
   loader). Wrap PG ops with `asyncio.run(...)` only at the outer
   entry-point — internal flows are already async.

4. Delete:
   - `shared/shared/store.py`
   - `data/labtfg.db` (and `data/` if empty)
   - Any `data/labtfg.db` reference in `.gitignore`.

5. Update `phase2-juan/README.md` (or the root CLAUDE.md "Running"
   section) to require Postgres. Note `docker compose up` covers it.

6. Add an integration test that the model loader works end-to-end
   reading from Postgres `models` table.

## Acceptance Criteria

- [x] AC1: `shared/shared/store.py` no longer exists.
- [x] AC2: `data/labtfg.db` no longer exists in the working tree.
      `.gitignore` references cleaned up.
- [x] AC3: `grep -rn 'shared.store\|shared\.store\.' phase2-juan/ shared/`
      returns zero matches.
- [x] AC4: Phase 2 CLI starts and lists models from Postgres.
      Integration test confirms.
- [x] AC5: Documentation explicitly states Postgres is required for
      Phase 2; no fallback path described.

## Files Likely Affected

- `shared/shared/store.py` — DELETE.
- `data/labtfg.db` — DELETE.
- `phase2-juan/simlab/model_loader.py` — migrate to Postgres async.
- `phase2-juan/simlab/cli.py` (or wherever `register_model` /
  `list_experiments` are called) — migrate.
- `phase2-juan/simlab/orchestrator.py` — migrate any remaining
  experiment-store calls.
- `phase2-juan/simlab/api.py` — same.
- `phase2-juan/README.md` (or root CLAUDE.md) — document requirement.
- `phase2-juan/tests/...` — add integration test.

## Context

Phase spec: `docs/specs/memory-refactor/phase-0-stop-lying.md` (R5)
General spec: `docs/specs/memory-refactor/general.md`
Source critique: `docs/memory-system.md` §A11
Heat: `registry`

## Completion Summary

**Commit:** `ed88176` — `feat[shared]: kill SQLite registry, require Postgres for Phase 2 (P0-005)`

### What was built
- Deleted `shared/shared/store.py` (sync sqlite3 registry).
- Deleted its tests: `phase2-juan/tests/test_store.py`,
  `shared/tests/test_store_extras.py`. Removed
  `test_store_backward_compat` from `shared/tests/test_lifecycle.py`.
- Removed `data/` from `.gitignore`. Deleted `data/labtfg.db` from the
  working tree.
- Updated `CLAUDE.md` Running section + `phase2-juan/docs/DESIGN.md`
  schema/tech sections to document Postgres-only operation. The
  DESIGN.md schema block now matches the actual `shared.models.Experiment`
  ORM (UUIDs, JSONB, S3 keys instead of inline JSON blobs).
- Added integration test `phase2-juan/tests/test_model_loader_postgres.py`
  that inserts a `Model` row through SQLAlchemy and verifies
  `discover_models()` reads it via the same `shared.db.get_session()`
  path the orchestrator uses in production. Uses an `@asynccontextmanager`
  shim so the test exercises the same contract as `DatabaseService`.

### Files created/modified
- `shared/shared/store.py` — DELETED.
- `phase2-juan/tests/test_store.py` — DELETED.
- `shared/tests/test_store_extras.py` — DELETED.
- `shared/tests/test_lifecycle.py` — removed legacy backward-compat test.
- `.gitignore` — dropped `data/` line.
- `CLAUDE.md` — Running section now requires `docker compose up`;
  `.env` now lists Postgres/MinIO/Neo4j/Qdrant settings explicitly.
- `phase2-juan/docs/DESIGN.md` — section 7 schema and tech rewritten
  for Postgres ORM; "Completado" list updated.
- `phase2-juan/tests/test_model_loader_postgres.py` — NEW integration
  test (2 cases: row present, empty table).

### Decisions
- Phase 2 simlab callers (orchestrator, model_loader, tools, api) were
  already on Postgres from prior P3-003 work — this issue was a
  cleanup-only strike, not a migration. The audit confirmed no live
  callers needed code changes.
- The integration test uses an `@asynccontextmanager` test shim
  rather than monkeypatching `shared.db` to a `DatabaseService` so we
  don't depend on `DatabaseService.connect()` succeeding (other infra
  unrelated to the test). The shim mirrors the contract exactly.
- Did not update `docs/memory-system.md` §A11 — it is the source
  critique document and historical record; the refactor it requested
  is now complete and the document remains as historical reference.

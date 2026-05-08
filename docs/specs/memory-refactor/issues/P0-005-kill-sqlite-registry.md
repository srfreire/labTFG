---
id: P0-005
title: Delete SQLite registry, migrate Phase 2 callers to Postgres
status: in-progress
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

- [ ] AC1: `shared/shared/store.py` no longer exists.
- [ ] AC2: `data/labtfg.db` no longer exists in the working tree.
      `.gitignore` references cleaned up.
- [ ] AC3: `grep -rn 'shared.store\|shared\.store\.' phase2-juan/ shared/`
      returns zero matches.
- [ ] AC4: Phase 2 CLI starts and lists models from Postgres.
      Integration test confirms.
- [ ] AC5: Documentation explicitly states Postgres is required for
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

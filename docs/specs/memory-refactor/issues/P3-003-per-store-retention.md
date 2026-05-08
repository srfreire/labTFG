---
id: P3-003
title: Per-store retention policies for MinIO, Postgres runs, Qdrant points, KG reflections
status: in-progress
kind: strike
phase: 3
heat: retention
priority: 2
blocked_by: [P2-004]
created: 2026-05-08
updated: 2026-05-08
---

# P3-003: Per-store retention policies

## Objective

Stop unbounded growth across the persistent stores. Define and apply
retention so the system stays sustainable past 6 months of CI: MinIO
bucket lifecycle for eval artifacts, Postgres `runs` archival of eval
runs, Qdrant cleanup script, KG reflection rollup.

## Requirements

Per phase spec R3:

1. **Postgres `runs` schema delta** — alembic revision adds
   `kind VARCHAR(10) NOT NULL DEFAULT 'prod'` (CHECK in `{prod,
   eval}`). Eval runner tags inserts with `kind='eval'`.
2. **MinIO lifecycle**:
   - In `docker-compose.yml`'s `minio-init` container, after bucket
     creation, run `mc ilm add` with rules:
     - Prefix `runs/eval/` expires after `RETENTION_EVAL_DAYS` (default 30).
     - Prefix `runs/prod/` expires after `RETENTION_PROD_DAYS` (default 365).
   - Existing keys without these prefixes are unaffected.
3. **PG eval-run archival** — add a CLI command
   `uv run cli_eval prune --older-than 30d` that:
   - Selects `runs WHERE kind='eval' AND created_at < NOW() - INTERVAL`.
   - Deletes them (cascade FK on `memories.run_id`,
     `node_run_observations.run_id`, `artifacts.run_id`).
   - Returns the count of deleted runs + cascaded rows.
4. **Qdrant purge** — `phase1-pablo/scripts/qdrant_purge_eval.py`:
   accepts a list of deleted `run_id`s (read from PG or stdin),
   deletes points whose payload `run_id` matches. Document the
   "PG prune → Qdrant purge" two-step in `docs/memory-system.md`.
5. **KG reflection rollup** — `phase1-pablo/scripts/kg_rollup_reflections.py`:
   monthly script that finds `Reflection` nodes older than 90 days,
   summarises them into a single `RollupReflection` node per
   month-cohort, deletes the originals. Idempotent.
6. **Retention reference doc** — new
   `docs/specs/memory-refactor/retention.md` documenting each policy,
   defaults, and run cadence.

## Acceptance Criteria

- [ ] AC1: Alembic revision adds `runs.kind` with default `prod` and
      a CHECK constraint. Up/down migrations both work.
- [ ] AC2: Eval driver tags new runs `kind='eval'`. Existing runs
      retain `prod`. Backfill optional but documented.
- [ ] AC3: `mc ilm export` shows the two lifecycle rules. Manual
      test: an object with prefix `runs/eval/test.txt` and a faked
      `--ttl 1m` rule expires.
- [ ] AC4: `cli_eval prune --older-than 30d` deletes eval runs and
      cascades. Manual test on dev DB shows expected counts.
- [ ] AC5: `qdrant_purge_eval.py` and `kg_rollup_reflections.py`
      run idempotently. `docs/specs/memory-refactor/retention.md`
      describes the full lifecycle.

## Files Likely Affected

- `shared/migrations/versions/<new>_runs_kind.py` — new.
- `shared/shared/models.py` — add `kind` to `Run`.
- `docker-compose.yml` — extend `minio-init` with lifecycle rules.
- `phase1-pablo/src/decisionlab/cli_eval.py` — add `prune` command.
- `phase1-pablo/src/decisionlab/eval/runner.py` — set
  `kind='eval'` on inserts.
- `phase1-pablo/scripts/qdrant_purge_eval.py` — new.
- `phase1-pablo/scripts/kg_rollup_reflections.py` — new.
- `docs/specs/memory-refactor/retention.md` — new.
- `docs/memory-system.md` — append a "Retention" section.

## Context

Phase spec: `docs/specs/memory-refactor/phase-3-data-integrity.md` (R3)
Heat: `retention` (independent of P3-001 / P3-002)

---
id: P3-003
title: Per-store retention policies for MinIO, Postgres runs, Qdrant points, KG reflections
status: done
kind: strike
phase: 3
heat: retention
priority: 2
blocked_by: [P2-004]
created: 2026-05-08
updated: 2026-05-09
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

- [x] AC1: Alembic revision adds `runs.kind` with default `prod` and
      a CHECK constraint. Up/down migrations both work.
- [x] AC2: Eval driver tags new runs `kind='eval'`. Existing runs
      retain `prod`. Backfill optional but documented.
- [x] AC3: `mc ilm export` shows the two lifecycle rules. Manual
      test: an object with prefix `runs/eval/test.txt` and a faked
      `--ttl 1m` rule expires.
- [x] AC4: `cli_eval prune --older-than 30d` deletes eval runs and
      cascades. Manual test on dev DB shows expected counts.
- [x] AC5: `qdrant_purge_eval.py` and `kg_rollup_reflections.py`
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

## Completion Summary

**Squash commit:** `d1dc367` — `feat[retention]: per-store retention policies (P3-003)`

**Branch commits (squashed):**
- `a0c6904` — `feat[shared]: add runs.kind column + cascade FKs (P3-003 AC1)`
- `79a5b26` — `feat[eval]: tag eval-driver Run inserts with kind='eval' (P3-003 AC2)`
- `3cbdd86` — `feat[infra]: add MinIO per-prefix lifecycle for eval/prod runs (P3-003 AC3)`
- `a570c6b` — `feat[eval]: add cli_eval prune for kind='eval' run retention (P3-003 AC4)`
- `918e11e` — `feat[shared]: add delete_by_run_ids + RollupReflection schema (P3-003 AC5)`
- `8e5b7eb` — `feat[retention]: add Qdrant purge + KG reflection rollup scripts (P3-003 AC5)`

### What was built

- **Postgres** — `runs.kind ∈ {prod, eval}` column with `CHECK` constraint
  (default `prod`). `ON DELETE CASCADE` on FKs from `memories`,
  `artifacts`, `node_run_observations`. Eval driver tags every new
  insert `kind='eval'`. `cli_eval prune --older-than <30d|24h|60m>`
  deletes expired eval runs, returns JSON with counts + deleted ids.
  `--dry-run` previews without touching the DB.
- **MinIO** — `minio-init` posts a 2-rule lifecycle on every boot via
  `mc ilm import`. `runs/eval/` expires after `RETENTION_EVAL_DAYS`
  (default 30); `runs/prod/` after `RETENTION_PROD_DAYS` (default 365).
  Idempotent — `mc ilm import` replaces the bucket's lifecycle wholesale.
- **Qdrant** — `scripts/qdrant_purge_eval.py` reads run_ids from stdin
  (the prune JSON, or a bare list, or one-per-line UUIDs) or from
  `--run-ids`, and filter-deletes points across `memories_dense`,
  `memories_sparse`, `artifacts_dense`, `artifacts_sparse`.
  `VectorStore.delete_by_run_ids()` issues a single filter delete per
  collection — no per-id round-trips. Idempotent on replay.
- **KG** — `scripts/kg_rollup_reflections.py` groups `Reflection` nodes
  older than `--older-than-days` (default 90) by `YYYY-MM` cohort,
  MERGEs each cohort into a `RollupReflection {id: "rollup:YYYY-MM"}`
  node (deduping `source_reflection_ids` server-side), and detach-
  deletes the originals. One managed transaction per cohort —
  merge + delete succeed together or fail together.
  `RollupReflection` joins the KG schema with a uniqueness constraint
  on `id` and an index on `month`.
- **Docs** — new `docs/specs/memory-refactor/retention.md` describing
  defaults, policies, cadence, and what is intentionally not pruned.
  `docs/memory-system.md` §A14 marked DONE with cross-link.

### Files created/modified

- `shared/migrations/versions/a99972f4b668_add_runs_kind_and_cascade_fks.py` — new.
- `shared/shared/models.py` — `Run.kind`, cascade FK names on `memories`/`artifacts`/`node_run_observations`.
- `shared/shared/vector_store.py` — `delete_by_run_ids()` helper, `FilterSelector` + `MatchAny` imports.
- `shared/shared/knowledge_graph.py` — `RollupReflection` schema entry.
- `shared/tests/test_models_constraints.py` — covers `runs_kind_check`.
- `docker-compose.yml` — `minio-init` lifecycle import.
- `phase1-pablo/src/decisionlab/cli_eval.py` — `prune` command + `_parse_duration`.
- `phase1-pablo/src/decisionlab/eval/runner.py` — `kind='eval'` on insert.
- `phase1-pablo/tests/eval/test_cli_eval.py` — `_parse_duration` table, prune help/validation.
- `phase1-pablo/tests/eval/test_runner_integration.py` — eval-driver kind assertion.
- `phase1-pablo/scripts/qdrant_purge_eval.py` — new.
- `phase1-pablo/scripts/kg_rollup_reflections.py` — new.
- `docs/specs/memory-refactor/retention.md` — new.
- `docs/memory-system.md` — §A14 update.

### Decisions

- **`delete_by_run_ids` lives on `VectorStore`, not in the script.**
  Reusable across future per-run-id purges (Phase 4 archival, ad-hoc
  prod-run cleanup). The script uses the public API rather than
  reaching into `shared.vectors._client`.
- **`RollupReflection` joins `_SCHEMA` rather than being created via
  raw Cypher.** Adding it to the schema dict gives a uniqueness
  constraint for free on the next `shared.init()` and keeps future
  KG consumers consistent.
- **Single-SET path in the rollup MERGE.** `ON CREATE SET … = []`
  followed by a single dedup-and-append `SET` makes the `merged`
  count consistent across CREATE and MATCH branches; no branch on
  `coalesce(rr.source_reflection_ids, [])` returning null.
- **Stdin parsing accepts dict / list / UUIDs-per-line.** The prune
  output is the dict form, but ad-hoc operators piping `jq -r
  '.run_ids[]'` or pasting UUIDs should also work without flag
  acrobatics.
- **Doc-only `prod` retention.** Prod runs never auto-delete from
  Postgres or MinIO past 365 days (lifecycle handles MinIO; PG keeps
  them forever). Removing a prod run is a manual op — documented in
  `retention.md`.

# Phase 3: Data integrity

> Status: current | Created: 2026-05-08 | Last updated: 2026-05-08
> References: [general.md](general.md) · [phases.md](phases.md) · [`docs/memory-system.md`](../../memory-system.md) §A6, §A14

## Objective

Stop the silent drift between Postgres `memories.confidence` and
Qdrant payload `confidence`. Today `apply_time_decay` syncs only
`memories_dense` (not sparse); `update_confidence` (corroborate /
contradict) syncs neither. Designate Postgres as the single source of
truth for confidence and read it at retrieval time. Then add per-store
retention so the system stays sustainable past 6 months of CI.

## Requirements

### R1 — Single confidence-write helper (A6 part 1)

Add `shared.memories.update_memory_confidence(session, id, *,
delta: float | None, set_to: float | None) -> float` that:
- Applies the change atomically via `UPDATE ... RETURNING confidence`.
- Clamps to `[0.1, 1.0]`.
- Returns the new value.

Refactor every confidence-write site to go through this helper:
- `touch_memory` (+0.02 access boost)
- `update_confidence` (+0.05 corroborate, -0.10 contradict)
- `apply_time_decay` (per-row decay)

The helper does **not** touch Qdrant — that's R2.

### R2 — Drop confidence from Qdrant payload, read at retrieve (A6 part 2)

Two changes:

1. Stop **writing** `confidence` in Qdrant payloads:
   - `indexer.index_stage_output` → drop `confidence` from the payload
     dict.
   - `consolidation` time-decay sync → delete the `set_payload` calls.
   - `resolver` enrichment path → drop `confidence` from the new
     vector's payload.

2. Read confidence from Postgres at retrieve time:
   - In `retrieval/tool.py:_apply_recency_weighting`, instead of
     reading `r.metadata.get("confidence", 1.0)`, batch-fetch all
     memory_ids from PG via `select(Memory.id, Memory.confidence)
     where Memory.id.in_(...)`. One round-trip, attach to results.
   - Memories without a PG row (artifact-only results) keep
     `confidence_factor = 1.0` (unchanged behaviour).

Migration: existing Qdrant payloads with stale `confidence` are
ignored — the field is read-only-then-delete. A separate alembic /
script-level cleanup pass can `set_payload({"confidence": null})` if
desired; not required.

### R3 — Per-store retention policies (A14)

Define and apply retention per persistent store:

- **MinIO**: bucket lifecycle policy expires objects with prefix
  `runs/eval/` after `RETENTION_EVAL_DAYS` (default 30), `runs/prod/`
  after `RETENTION_PROD_DAYS` (default 365). Configured via
  `mc lifecycle add` in the `minio-init` container or a one-shot
  bootstrap script.
- **Postgres `runs`**: add a column `kind ∈ {prod, eval}` (default
  `prod`); eval driver tags inserts with `kind=eval`. Cron-style
  archival job (or one-shot script) deletes eval runs older than
  `RETENTION_EVAL_DAYS`, cascading to `memories.run_id` (FK already
  set up).
- **Qdrant**: cleanup script (`scripts/qdrant_purge_eval.py`) that
  deletes points whose payload `run_id` corresponds to a
  PG-deleted eval run. Not automatic — invoked from CI nightly.
- **KG `Reflection` rollup**: monthly script that summarises old
  reflections (>90d) into a single `RollupReflection` node and
  deletes the originals.

Document in `docs/memory-system.md` and in a new
`docs/specs/memory-refactor/retention.md`.

## Acceptance Criteria

- [ ] AC1: `update_memory_confidence` exists in `shared.memories` with
      atomic `UPDATE ... RETURNING`. All three call sites
      (`touch_memory`, `update_confidence`, `apply_time_decay`) route
      through it. Unit tests cover clamp boundaries.
- [ ] AC2: New writes to `memories_dense` and `memories_sparse` no
      longer include `confidence` in payload. Integration test asserts
      payload shape.
- [ ] AC3: `_apply_recency_weighting` fetches confidences from PG in
      one batched query; drops the `metadata.confidence` read.
      Unit test asserts the SQL query is issued exactly once per
      retrieve.
- [ ] AC4: MinIO lifecycle rule visible via `mc ilm export`; PG `runs`
      table has a `kind` column with eval driver tagging inserts.
      Cron/one-shot deletion script exists and is documented.
- [ ] AC5: Manual eval-cleanup run on a populated dev DB removes
      `kind=eval` runs older than 30 days and cascades to
      `memories`. Qdrant purge script removes the corresponding
      points.

## Technical Notes

- **Heats**:
  - `confidence` (R1, R2) — sequential. R1's helper must exist before
    R2 drops the Qdrant payload reads.
  - `retention` (R3) — independent of R1/R2.
- **Latency check after R2**: adds one PG round-trip per retrieve.
  Phase 2 must have headroom (≤2.5s p95) for this to land safely.
  If retrieve latency creeps back over budget after R2, profile and
  consider keeping confidence read-only on Qdrant payload as a cache.

## Decisions

- **Drop Qdrant confidence outright** (vs. dual-write helper). One
  source of truth is cleaner long-term. The PG round-trip cost is
  bounded (<5ms for in-list lookups on indexed UUID PKs).
- **Retention as policy, not deletion code in the hot path**. A
  monthly cron job or manual `cli_eval prune` is enough — no need
  for in-process retention logic.
- **Tag eval runs with `kind=eval`** rather than a separate table.
  Smaller schema delta; existing FKs cascade naturally.

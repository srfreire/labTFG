# Retention policies (memory-refactor P3-003 / phase-3 R3)

> Created: 2026-05-09 · Last updated: 2026-05-09
> Source: [phase-3-data-integrity.md](phase-3-data-integrity.md) §R3 ·
> [`docs/memory-system.md`](../../memory-system.md) §A14

## Why

Without retention every CI run leaves debris. Cumulative-growth and
slug-accuracy add ~700 graph elements per day; eval `runs` rows and the
MinIO objects they point at grow forever. After 6 months the eval suite
is auditing as much eval pollution as production behaviour.

Each store gets its own policy. The defaults below are tuned to keep
roughly one quarter of eval data (so a regression has time to be
reproduced) and one year of production data (long enough to compare
against quarterly memoria milestones).

## Defaults

| Variable | Default | Effect |
|---|---|---|
| `RETENTION_EVAL_DAYS` | 30 | MinIO `runs/eval/` prefix expiry; `cli_eval prune --older-than` default. |
| `RETENTION_PROD_DAYS` | 365 | MinIO `runs/prod/` prefix expiry. |
| `RETENTION_REFLECTION_DAYS` | 90 | KG `Reflection` rollup cutoff (script flag). |

All three are overridable per environment. The MinIO defaults are
threaded through `docker-compose.yml`'s `minio-init` container; the
others are CLI / script flags only (no implicit per-process retention).

## Policies

### MinIO — bucket lifecycle (automatic)

`minio-init` posts a 2-rule lifecycle to the `labtfg` bucket on every
boot via `mc ilm import`:

- Prefix `runs/eval/` → expire after `RETENTION_EVAL_DAYS`.
- Prefix `runs/prod/` → expire after `RETENTION_PROD_DAYS`.

Objects outside these prefixes (e.g. `kg_entities/…`, `seed/…`) are
untouched. Re-running `minio-init` is idempotent — `mc ilm import`
replaces the bucket's lifecycle wholesale, so no duplicate rules
accumulate.

**Verify**: `mc ilm export local/labtfg` shows both rules.
**Manual test**: drop an object at `runs/eval/test.txt`, set a 1-minute
expiry rule, observe it disappears after the next MinIO scan.

### Postgres `runs` — `cli_eval prune` (manual / scheduled)

Phase 1 runs are tagged with `kind ∈ {prod, eval}` (default `prod`).
The eval driver tags inserts `kind='eval'`. The prune CLI deletes
old eval runs and cascades through the existing `ON DELETE CASCADE`
FKs to `memories`, `artifacts`, and `node_run_observations`:

```bash
uv run cli_eval prune --older-than 30d           # delete
uv run cli_eval prune --older-than 30d --dry-run # preview only
```

Output is JSON with the cutoff, the deleted-run ids, and per-table
cascade counts. `--dry-run` returns the same shape without touching
the database — feed either into the Qdrant purge below.

`prod`-kind runs are never auto-deleted from Postgres. If a prod run
needs to be removed, do it manually (and pipe its id through the Qdrant
purge below).

### Qdrant — `qdrant_purge_eval.py` (manual, downstream of PG prune)

The PG prune above only deletes rows in Postgres. Qdrant points carry
`run_id` in their payload (`memories_*` and `artifacts_*` collections),
so they have to be purged in a second step:

```bash
uv run cli_eval prune --older-than 30d \
  | uv run scripts/qdrant_purge_eval.py
```

The script reads `run_ids` from stdin (the prune output), or from
`--run-ids uuid1,uuid2`, and issues a filter-based delete against each
collection. Idempotent — re-running with the same ids is a no-op. A
`--dry-run` flag prints the plan without modifying Qdrant.

Collections purged: `memories_dense`, `memories_sparse`,
`artifacts_dense`, `artifacts_sparse`. `kg_entities_dense` is **not**
touched — it indexes KG entities, not run-scoped points.

### KG `Reflection` rollup — `kg_rollup_reflections.py` (monthly)

Reflection nodes accumulate in the graph (one per consolidation
cluster). After 90 days, individual reflections are rarely
queried — what matters is the cohort. The rollup script:

1. Finds `Reflection` nodes with `created_at < now - 90d`.
2. Groups them by `YYYY-MM` cohort.
3. For each cohort, MERGEs a `RollupReflection {id: "rollup:YYYY-MM"}`
   node, appending only the source IDs not already present.
4. Detach-deletes the originals.

Each cohort runs in a single managed transaction — merge and delete
succeed together or both fail together. Re-running picks up exactly
the reflections that became old since the last run.

```bash
uv run scripts/kg_rollup_reflections.py
uv run scripts/kg_rollup_reflections.py --older-than-days 60 --dry-run
```

The `RollupReflection` node carries `month`, `count`,
`source_reflection_ids` (deduped), `created_at`, and `last_rolled_up_at`.
Future graph traversals can either ignore it (preserve historical
behaviour) or include it (cohort-level retrieval).

## Cadence

| Policy | Trigger |
|---|---|
| MinIO lifecycle | Automatic — MinIO scans hourly. |
| `cli_eval prune` | Nightly CI cron, or before each release. |
| `qdrant_purge_eval.py` | Pipe-after-prune in the same cron job. |
| `kg_rollup_reflections.py` | Monthly cron (e.g. 1st of each month). |

The two-step PG-then-Qdrant pipe is the only ordering constraint that
matters: the prune outputs the run_ids that the purge needs as input.
Reverse the order and the Qdrant purge has no source of truth for
which runs are gone.

## What is NOT pruned

- **`prod`-kind Postgres runs.** No automatic deletion. Manual only.
- **`models` table** rows referenced by prod runs (FK is `nullable`).
- **`kg_entities_dense`** Qdrant points. KG entities are reused
  across runs — pruning by `run_id` would orphan paradigm/variable
  embeddings.
- **Non-`Reflection` KG nodes** (Paradigm, Variable, Postulate,
  Formulation, Model). These are knowledge, not observations; they
  outlive runs by design.
- **Stale `confidence` payloads in Qdrant.** Phase-3 R2 stops writing
  them but does not back-fill old points. A separate one-shot pass
  can `set_payload({"confidence": null})` if desired; not required.

## Files

| Concern | File |
|---|---|
| `runs.kind` column + cascade FKs | `shared/migrations/versions/a99972f4b668_add_runs_kind_and_cascade_fks.py` |
| Eval-run tagging | `phase1-pablo/src/decisionlab/eval/runner.py` |
| MinIO lifecycle init | `docker-compose.yml` (`minio-init`) |
| PG eval-run prune | `phase1-pablo/src/decisionlab/cli_eval.py::cli_eval_prune` |
| Qdrant purge | `phase1-pablo/scripts/qdrant_purge_eval.py` |
| KG reflection rollup | `phase1-pablo/scripts/kg_rollup_reflections.py` |
| `RollupReflection` schema | `shared/shared/knowledge_graph.py::_SCHEMA` |
| `delete_by_run_ids` helper | `shared/shared/vector_store.py` |

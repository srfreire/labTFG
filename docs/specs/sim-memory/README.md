# sim-memory

Phase 2 feature that writes Tracker observations into the Knowledge Backbone (Postgres + Qdrant) so future Phase 1 pipeline runs can learn from past simulation outcomes.

For the authoritative design, see:

- [general.md](general.md) — overview, data model, integrations, decisions.
- [phase-1-core-writer.md](phase-1-core-writer.md) — `TrackerMemoryWriter` internals.
- [phase-2-integration.md](phase-2-integration.md) — flag, singleton, orchestrator wiring.

## Quick reference

| Setting | Default | Purpose |
|---|---|---|
| `ENABLE_KNOWLEDGE_WRITE` | `false` | Master switch. When `true`, `shared.sim_memory_writer` is wired during `shared.init()`. |
| `VOYAGE_API_KEY` | — | Required for embeddings. If empty the writer is `None`. |
| `ZEROENTROPY_API_KEY` | — | Required by `EmbeddingService`. If empty the writer is `None`. |
| `POSTGRES_DSN` / `QDRANT_URL` | dev defaults | Writer reuses the already-connected `shared.db` / `shared.vectors`. |

Acceptable truthy values for `ENABLE_KNOWLEDGE_WRITE`: `1`, `true`, `yes`, `on` (case-insensitive).

## Manual end-to-end verification

Use this procedure when preparing a release to confirm the full write path works against real infrastructure. Unit tests cover everything else; this is for the wiring you can only validate with live services.

### 1. Start infrastructure

```bash
docker compose up -d postgres qdrant
```

Wait for both to be healthy. Verify with:

```bash
docker compose ps
```

### 2. Apply migrations

```bash
cd shared
uv run alembic upgrade head
```

This ensures the `memories` table exists with the columns used by `shared.memories.create_memory`.

### 3. Configure environment

In `phase2-juan/.env` (or the project root `.env`):

```
VOYAGE_API_KEY=...
ZEROENTROPY_API_KEY=...
ENABLE_KNOWLEDGE_WRITE=true
```

### 4. Run a full simulation

```bash
cd phase2-juan
uv run simlab
```

Ask the chat to:

1. Create a small environment (e.g. `grid 8x8 with 5 food patches`).
2. Run a simulation with one model, 2 agents, 50 steps.
3. Observe the simulation.

Look for this log line from the orchestrator:

```
sim-memory: wrote N summaries, N trajectories, N episodes (filtered=N, skipped=None, NNms)
```

### 5. Verify Postgres

```sql
SELECT namespace, memory_type, source_stage, count(*)
FROM memories
WHERE namespace = 'simulation'
GROUP BY 1, 2, 3;
```

Expected:

| namespace | memory_type | source_stage | count |
|---|---|---|---|
| simulation | semantic | tracker | ≥ 1 |
| simulation | episodic | tracker | ≥ 0 |

Inspect one row:

```sql
SELECT content, importance, confidence, metadata
FROM memories
WHERE namespace = 'simulation'
ORDER BY created_at DESC
LIMIT 1;
```

`metadata` must contain `phase2_experiment_id`, `paradigm`, `formulation`, `model_class_name`, `environment`, `steps`, `seed`.

### 6. Verify Qdrant

```bash
curl -sX POST http://localhost:6333/collections/memories_dense/points/scroll \
  -H 'Content-Type: application/json' \
  -d '{
    "filter": {"must": [{"key": "namespace", "match": {"value": "simulation"}}]},
    "limit": 5,
    "with_payload": true
  }' | jq '.result.points[] | {id, payload}'
```

Each point should have a UUID `id` matching a row in the Postgres `memories` table and a payload containing `paradigm` + `formulation`.

Same check against `memories_sparse`:

```bash
curl -sX POST http://localhost:6333/collections/memories_sparse/points/scroll \
  -H 'Content-Type: application/json' \
  -d '{
    "filter": {"must": [{"key": "namespace", "match": {"value": "simulation"}}]},
    "limit": 5
  }' | jq '.result.points | length'
```

Expected: equal to the count in Postgres (may be less if any fact tokenised to an empty sparse vector — acceptable).

### 7. Run the Phase 1 integration test

With the same infra still up and keys exported:

```bash
cd phase2-juan
uv run pytest tests/knowledge/test_integration.py -m integration -v
```

This writes a temporary experiment, verifies round-trip through Postgres + Qdrant, and cleans up after itself.

## Disabling the feature

Set `ENABLE_KNOWLEDGE_WRITE=false` (or omit it) and restart. The orchestrator code path for the writer short-circuits via `getattr(shared, "sim_memory_writer", None) is None`, with no behavioural difference from pre-sim-memory main.

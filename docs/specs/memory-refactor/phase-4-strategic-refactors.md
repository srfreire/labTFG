# Phase 4: Strategic refactors

> Status: current | Created: 2026-05-08 | Last updated: 2026-05-08
> References: [general.md](general.md) · [phases.md](phases.md) · [`docs/memory-system.md`](../../memory-system.md) §A2, §A3, §A7, §A9

## Objective

Pay down the architectural debt that Phase 0–3 work around. Drop the
module-level `shared.kg/vectors/embeddings` singletons in favor of a
`Services` context object passed explicitly. Collapse the redundant
Qdrant `artifacts_*` collections and move `kg_entities_dense` into
Neo4j's native vector index. Split the overloaded `memories` table by
phase. Designate Postgres `memories` as the single temporal source of
truth and reduce Neo4j relations to identity-only triples linked back
by `memory_id`.

**Deferrable past TFG submission.** Phases 0–3 alone deliver green
tests + retrieval in budget + clean confidence semantics. Phase 4 is
the rewrite that future-you should do once the TFG ships.

## Requirements

### R1 — `Services` context replaces module-level singletons (A7)

Today every infra consumer does `import shared; shared.kg.do_x()`.
The test seams (`_get_kg`, `_get_vector_store`,
`_get_embedding_service`) exist precisely to support
monkeypatching — they are workarounds for bad architecture.

Replace with a `Services` dataclass:

```python
@dataclass(frozen=True)
class Services:
    kg: KnowledgeGraph | None
    vectors: VectorStore | None
    embeddings: EmbeddingService | None
    db: DatabaseService
    storage: StorageService
```

Wire it through every entry point (CLI, FastAPI app, test fixtures).
Module-level globals in `shared/__init__.py` retained as a backwards-
compat shim **only for the duration of this issue** — final commit
deletes them.

Bonus: removes the import cycle in `_init_sim_memory_writer` (which
imports `simlab.knowledge` from `shared/__init__.py`).

### R2 — Collapse `artifacts_*` Qdrant collections + move `kg_entities` to Neo4j vector index (A9)

`artifacts_dense` + `artifacts_sparse` are a search index over MinIO
content that nothing in the agent loop actually queries — they
duplicate raw stage output without a lifecycle. Delete both
collections.

`kg_entities_dense` is a manual mirror of slug-like KG nodes used by
retrieval's `_link_entities_ann`. Neo4j 5 supports native vector
indexes:

```cypher
CREATE VECTOR INDEX paradigm_embedding_idx IF NOT EXISTS
FOR (n:Paradigm) ON (n.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 1024,
  `vector.similarity_function`: 'cosine'
}}
```

Migrate: write embeddings to `n.embedding` during `kg_writer`'s ANN
sync (already runs there), query via Cypher
`db.index.vector.queryNodes(...)` from retrieval. Delete the
`kg_entities_dense` collection and the `_get_vector_store()` calls
in `kg_writer.py:457`.

### R3 — Split `memories` table by phase (A2)

Today `memories` carries Phase 1 lifecycle columns (importance,
confidence, corroborations, supersession) and Phase 2 fixed-confidence
observations (`run_id=NULL`, JSONB metadata for cross-phase joins).
Split into:

```
pipeline_memories (everything Phase 1 currently writes)
  - all current columns
  - run_id NOT NULL (FK runs.id)

simulation_observations (everything Phase 2 currently writes)
  - id, content, namespace='simulation'
  - phase2_experiment_id, paradigm, formulation, model_class_name
  - phase1_run_id (FK runs.id, nullable)
  - importance, confidence (fixed values), created_at
  - drop: corroborations, contradictions, valid_to, superseded_by
    (Phase 2 doesn't use them)
```

Both feed the same `memories_dense/sparse` Qdrant collections. Add a
`source_kind ∈ {pipeline, simulation}` field to the Qdrant payload so
retrieval can route reads back to the correct table.

### R4 — Single temporal source of truth (A3)

Designate Postgres `pipeline_memories` as the source of truth for
temporal validity. Strip Neo4j relations down to identity-only:

- Remove `valid_from`, `valid_to`, `confidence`, `run_id` from
  Cypher relation properties.
- Add `memory_id UUID` (FK semantically — Neo4j won't enforce, but
  retrieval queries always join through PG first).
- Temporal queries become two-step:
  1. PG: `SELECT id FROM pipeline_memories WHERE valid_from <= $as_of
     AND (valid_to IS NULL OR valid_to > $as_of)`.
  2. Neo4j: `MATCH ()-[r]->() WHERE r.memory_id IN $valid_ids ...`.

Migration: existing Neo4j relations carry their old props; backfill
script extracts each into a `pipeline_memories` row with the same
UUID, then sets `r.memory_id = $uuid` and clears the temporal
properties in a follow-up Cypher pass.

Depends on R3 — `pipeline_memories` must exist before R4 can rewrite
relation semantics.

## Acceptance Criteria

- [ ] AC1: `Services` dataclass exists; every Phase 1 / Phase 2 entry
      point constructs and threads it. Module-level
      `shared.kg/vectors/embeddings` deleted in the same PR. Phase 1
      ↔ Phase 2 import cycle resolved (no `simlab` import inside
      `shared/__init__.py`).
- [ ] AC2: `artifacts_dense` + `artifacts_sparse` Qdrant collections
      deleted. `kg_entities_dense` deleted; Neo4j has a vector index
      on `Paradigm.embedding` (and Variable, Postulate, Formulation,
      Model). Retrieval entity-link uses `db.index.vector.queryNodes`.
- [ ] AC3: `pipeline_memories` and `simulation_observations` exist
      via alembic. `memories` table renamed/migrated; FKs and indexes
      preserved. Phase 1 writers target `pipeline_memories`; Phase 2
      `TrackerMemoryWriter` targets `simulation_observations`. Both
      feed the same Qdrant collections with `source_kind` payload.
- [ ] AC4: Neo4j relations no longer carry temporal props. Two-step
      temporal queries pass an integration test
      (`test_temporal_consistency.py`) that confirms PG and KG agree
      for an `as_of` query against a multi-version dataset.
- [ ] AC5: Full eval suite (smoke + cumulative-growth +
      slug-accuracy) green after the migration. No retrieval
      regressions vs. Phase 3 baseline.

## Technical Notes

- **Heats**:
  - `infra` (R1) — independent, but touches the most files.
  - `vectors` (R2) — independent.
  - `data-model` (R3 → R4) — sequential. R4 depends on
    `pipeline_memories` existing.
- **Risk profile**: R1 is high-touch but low-risk per file (mechanical
  refactor). R2 deletes data — backup Qdrant collections before
  delete. R3 is a schema rename; lock writes during migration. R4
  rewrites every Neo4j relation; do it in a one-shot script with
  resume semantics.
- **Defer in TFG?** Yes if time-constrained. Document the deferred
  state in `phases.md` and ship Phases 0–3.

## Decisions

- **`Services` dataclass over a DI framework**. Plain Python; no new
  dependency. Tests construct `Services(kg=FakeKG(), ...)` directly.
- **Drop `artifacts_*` rather than make them queryable**. Nothing
  reads them today; deleting is cheaper than building a use case.
- **Neo4j as identity-only after R4**. Graph is the right structure
  for relations between entities; Postgres is the right structure for
  versioned facts about those relations. Stop trying to do both in
  Neo4j.
- **R4 is the only one that can leave the system in a half-migrated
  state mid-PR**. Bundle it as a single big strike with
  worktree isolation; don't slice further.

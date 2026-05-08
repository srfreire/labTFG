# Persistent Memory System — Accurate Snapshot

> Source-of-truth audit by direct code/spec read, **not** the architecture overview.
> Generated: 2026-05-08. Reflects state on `main` after commit `b971e6d`.

---

## 1. Stores at a glance

The "persistent memory" of labTFG is **five physical stores** working together.
Four of them live in `docker-compose.yml`; one is a local SQLite file used only
by Phase 2.

| # | Store | Image / file | Role | Wired in |
|---|---|---|---|---|
| 1 | **Postgres 17** | `postgres:17-alpine` (port 5432) | Relational lifecycle of memories, runs, models, experiments, artifacts | `shared.database.DatabaseService` (SQLAlchemy 2.0 async) |
| 2 | **Neo4j 5 community** | `neo4j:5-community` (7474/7687, APOC) | Knowledge graph: paradigms, papers, equations, postulates… and their relations | `shared.knowledge_graph.KnowledgeGraph` |
| 3 | **Qdrant** | `qdrant/qdrant:latest` (6333/6334) | 5 collections: dense (Voyage 1024d) + sparse (BM25 native, IDF) | `shared.vector_store.VectorStore` |
| 4 | **MinIO** | `minio/minio:latest` (9000/9001), bucket `labtfg` | Raw artifact bytes (reports, formulations, code, PDFs, charts, tracker JSON) | `shared.storage.StorageService` (aioboto3) |
| 5 | **SQLite** | `data/labtfg.db` (local file, WAL) | Phase-2-only registry of dynamically loaded models + experiments | `shared.store` (sync sqlite3) |

External dependencies wired in but **not** persistent storage:

| Service | Purpose |
|---|---|
| Voyage AI | `voyage-4-large` (docs, 1024d) + `voyage-4-lite` (queries, asymmetric) |
| ZeroEntropy | `zerank-2` rerank |
| Anthropic | Haiku 4.5 (Formalizer/Builder extraction, importance, CRAG, NER, reflections — `knowledge_fast_model`) + Sonnet 4.6 (Researcher/Reasoner extraction, conflict resolution — `knowledge_structured_model`) |

Bootstrap lives in `shared/shared/__init__.py`:
- `init()` connects Postgres, MinIO, Neo4j, Qdrant, Voyage/ZE.
- Each component **degrades independently** — Neo4j down ≠ Qdrant down. Missing deps log a warning and the corresponding module-level singleton stays `None`.
- `_init_sim_memory_writer()` wires the Phase 2 `TrackerMemoryWriter` only when `ENABLE_KNOWLEDGE_WRITE=true` *and* Qdrant + Voyage + Postgres are all up.

Two feature flags gate behaviour:
- `ENABLE_KNOWLEDGE_WRITE` — Phase 2 simulation memories writer.
- `ENABLE_KNOWLEDGE_READ` — Phase 2 agents calling `retrieve_context`.

---

## 2. Postgres — `shared/shared/models.py`

Five tables. SQLAlchemy 2.0 async. All UUID PKs. Migrations under
`shared/migrations/versions/`.

### 2.1 `runs` — Phase 1 pipeline runs

```
runs
├─ id              UUID PK
├─ created_at      TIMESTAMP server_default=now()
├─ problem_description  TEXT
├─ status          VARCHAR(50)   default 'created'
├─ s3_report_key   VARCHAR(500)  nullable
├─ s3_prefix       VARCHAR(500)
├─ artifact_count  INTEGER       nullable
├─ final_stage     VARCHAR(50)   nullable
└─ memory_results  JSONB         nullable   # per-stage MemoryAgentResult counters
```

### 2.2 `models` — generated Phase 1 decision models

```
models
├─ id              UUID PK
├─ class_name      VARCHAR(255)
├─ paradigm        VARCHAR(255)
├─ formulation     VARCHAR(255)
├─ description     TEXT          nullable
├─ run_id          UUID FK → runs.id   nullable
├─ s3_model_key    VARCHAR(500)
├─ s3_test_key     VARCHAR(500)  nullable
├─ registered_at   TIMESTAMP server_default=now()
└─ metadata        JSONB         nullable
   UNIQUE (run_id, paradigm, formulation)
```

### 2.3 `experiments` — Phase 2 simulations

```
experiments
├─ id              UUID PK
├─ created_at, updated_at  TIMESTAMP
├─ description     TEXT
├─ status          VARCHAR(50)   default 'created'
├─ spec, models_used   JSONB
├─ steps, seed     INTEGER       nullable
└─ s3_*_key        VARCHAR(500)  (events, replay, tracker, analyst, pdf, tex)
   s3_charts_prefix  VARCHAR(500)
```

### 2.4 `artifacts` — pointer table for MinIO objects

```
artifacts
├─ id              UUID PK
├─ s3_key          VARCHAR(500)  UNIQUE
├─ artifact_type   VARCHAR(50)
├─ run_id          UUID FK → runs.id          nullable
├─ experiment_id   UUID FK → experiments.id   nullable
├─ size_bytes      INTEGER
├─ content_type    VARCHAR(100)
└─ created_at      TIMESTAMP
```

### 2.5 `memories` — core lifecycle table (the heart of the system)

```
memories
├─ id              UUID PK
├─ content         TEXT
├─ namespace       VARCHAR(50)        ix_memories_namespace
│                  ∈ {paradigm, formulation, model, simulation, meta}
├─ memory_type     VARCHAR(50)
│                  ∈ {semantic, episodic, procedural, reflection}
├─ source_stage    VARCHAR(100)       ix_memories_source_stage
│                  ∈ {researcher, formalizer, reasoner, builder, tracker, memory_agent}
├─ run_id          UUID FK → runs.id  ix_memories_run_id   nullable
├─ created_at, updated_at   TIMESTAMP
├─ last_accessed_at TIMESTAMP nullable
├─ access_count    INTEGER   default 0
├─ importance      FLOAT     (1–10)
├─ confidence      FLOAT     (0.1–1.0, clamped)   ix_memories_confidence
│                                                  ix_memories_ns_confidence (composite)
├─ corroborations  INTEGER   default 0
├─ contradictions  INTEGER   default 0
├─ valid_from      TIMESTAMP server_default=now()
├─ valid_to        TIMESTAMP nullable             ix_memories_valid_to
├─ superseded_by   UUID FK → memories.id   nullable
└─ metadata        JSONB     nullable
```

**Lifecycle helpers** — `shared/shared/memories.py`:

| Function | Effect on `confidence` |
|---|---|
| `create_memory()` | initial = stage default (researcher 0.6, formalizer 0.7, reasoner 0.8, builder 0.9; tracker fixed 0.80) |
| `touch_memory()` | +0.02 (capped at 1.0), bumps `access_count`, sets `last_accessed_at` |
| `update_confidence(corroborate=True)` | +0.05 (capped 1.0), `corroborations += 1` |
| `update_confidence(contradict=True)` | −0.10 (floored 0.1), `contradictions += 1` |
| `supersede_memory()` | sets old `valid_to=now()` + `superseded_by`, inserts new row |
| `apply_time_decay()` | for non-reflections inactive ≥30d: `confidence *= 0.95^periods` |
| `get_memories_at_time(as_of)` | temporal validity filter — what was true at *as_of* |
| `get_supersession_chain(id)` | walks `superseded_by`, cycle-safe, capped at 1000 |

---

## 3. Neo4j — `shared/shared/knowledge_graph.py`

11 node labels, 11 relation types. Schema and allowed identifiers are
**hard-coded whitelists** — `_check_label`, `_check_rel_type`, `_check_ident`
guard every Cypher write to prevent injection.

### 3.1 Nodes

```
Label          unique_key       additional indexes
─────────────  ───────────────  ─────────────────────
Paradigm       slug             [name]
Variable       id               [paradigm_slug, name]      ← composite id = "{paradigm}:{slugify(name)}"
Equation       latex
BrainRegion    name
Author         name
Paper          doi
Postulate      id
Formulation    id
Parameter      name
Model          formulation_id
Reflection     id
```

The `Variable.id` composite was introduced in commit `50c952c` — same name
under two paradigms can no longer collide. Orphans (no paradigm) are
namespaced as `orphan:{slug}`.

### 3.2 Relations

```
Relation         Direction
───────────────  ───────────────────────────────
SUPPORTS         Paper → Postulate
CONTRADICTS      Paper → Postulate
EXTENDS          Paradigm → Paradigm
MEASURES         Variable → BrainRegion
MODULATES        Variable → Variable
AUTHORED         Author → Paper
DERIVES_FROM     Parameter → Postulate
IMPLEMENTS       Model → Formulation
USES_EQUATION    Formulation → Equation
BELONGS_TO       Postulate → Paradigm
CITES            Paper → Paper
```

Every relation carries temporal metadata: `created_at`, `valid_from`,
`valid_to`, `run_id`. **Nothing is hard-deleted.** Supersession is the
write pattern (Zep style):

```cypher
MATCH (a)-[r:REL]->(b) WHERE r.valid_to IS NULL ...
// if existing != new (excluding _TEMPORAL_KEYS) → SET r.valid_to = $now
CREATE (a)-[r2:REL $new_props]->(b)
```

### 3.3 Node-write guarantees

`decisionlab/knowledge/kg_writer.py:populate_kg`:

- **Per-node** managed-write transactions (a single failed `Paper.doi`
  collision no longer voids the whole topic — the cumulative-growth t1
  regression).
- **MERGE on natural key** with `n.run_ids = coalesce(n.run_ids, []) + run_id`
  so cross-run provenance accumulates.
- **`_validate_natural_key`** rejects:
  - UUID-shaped slugs on `_SLUG_LIKE_LABELS = {Paradigm, Variable, Postulate, Formulation, Model, BrainRegion}` (catches `run_id` leaks).
  - Keys >80 chars (catches LLM blobs promoted to keys).
  - Slugs that re-slugify to empty.
- **`_resolve_natural_key`** priority: schema unique key → declared
  natural_key → fallback (`slug, id, doi, url, name, title`) → synthetic
  hash (`_synthetic_id = h_<sha1[:16]>`).
- **ANN sync (best-effort, fire-and-forget):** slug-like nodes are pushed to
  `kg_entities_dense` so retrieval can entity-link via vector lookup
  instead of an O(N) Cypher scan.

### 3.4 Temporal queries

`KnowledgeGraph.query_at_time(cypher, as_of)` injects
`WHERE r.valid_from <= $_as_of AND (r.valid_to IS NULL OR r.valid_to > $_as_of)`
before the `RETURN` clause. `get_node_history(label, key, value)` returns all
versions ordered by `valid_from`.

---

## 4. Qdrant — `shared/shared/vector_store.py`

**5 collections.** All dense use cosine distance, dim 1024 (Voyage). All
sparse use Qdrant's native BM25 (`Qdrant/bm25` model) with
`Modifier.IDF` — tokenization is FastEmbed client-side, IDF + TF
saturation + length normalization is server-side. **No custom tokenizer.**

| Collection | Type | Dim | Source content |
|---|---|---|---|
| `artifacts_dense` | dense | 1024 | Pipeline stage output chunks (researcher reports, formulations, reasoner specs, builder code) |
| `artifacts_sparse` | sparse | — | Same chunks, BM25 representation |
| `memories_dense` | dense | 1024 | Extracted facts (Phase 1) + simulation observations (Phase 2) |
| `memories_sparse` | sparse | — | Same facts, BM25 representation |
| `kg_entities_dense` | dense | 1024 | Slug-like KG nodes for fast entity linking |

### 4.1 Payload schema (every point)

```json
{
  "entity_id":     "<uuid>",
  "namespace":     "paradigm | formulation | model | simulation | meta",
  "source_stage":  "researcher | formalizer | reasoner | builder | tracker | memory_agent",
  "run_id":        "<phase1 run uuid>",
  "importance":    1.0..10.0,
  "confidence":    0.0..1.0,
  "created_at":    "<iso8601>",
  "text_preview":  "<first 200 chars>"
}
```

Phase 2 simulation memories add the rich cross-phase metadata defined in
`docs/specs/sim-memory/general.md`: `phase2_experiment_id`, `model_id`,
`model_class_name`, `paradigm`, `formulation`, `phase1_run_id`,
`environment`, `steps`, `seed`, plus `agent_id`, `episode_type`, `step` for
trajectory/episode rows.

### 4.2 Filter syntax

`_build_filter()` in `vector_store.py:227` — accepts:
- `{key: value}` → exact match (must)
- `{key: {gte: x, lte: y}}` → range
- `{"_exclude": {k: v}}` → must_not

---

## 5. MinIO — `shared/shared/storage.py`

S3-compatible. Bucket `labtfg`. `aioboto3` async client. Stores raw bytes;
the relational/graph/vector stores hold processed knowledge derived from
these objects. Keys are tracked in the `artifacts` Postgres table.

---

## 6. SQLite (`data/labtfg.db`) — `shared/shared/store.py`

Local file, WAL mode, **Phase 2 only**. Two tables:

| Table | Purpose |
|---|---|
| `models` | Dynamically discovered Phase 1 decision models (formulation_id, class_name, paradigm, file_path, metadata_json) |
| `experiments` | Local experiment registry mirroring the Postgres `experiments` schema (used when running Phase 2 standalone without Postgres) |

Looked up by walking up to the directory containing `CLAUDE.md`.

---

## 7. Write path — Memory Agent (Phase 1, after each stage)

```
Pipeline stage finishes
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│  decisionlab.knowledge.extraction.extract(stage, output)          │
│  • Stage-specific prompt (RESEARCHER / FORMALIZER / REASONER /    │
│    BUILDER) + tiered model via call_structured (forced tool-use): │
│    Researcher+Reasoner → knowledge_structured_model (Sonnet),     │
│    Formalizer+Builder  → knowledge_fast_model (Haiku)             │
│  • Pydantic-validated envelope: {nodes, relations, facts}         │
│  • _fold_legacy_test_results — folds old TestResult into Model    │
│  • _is_garbage_paradigm_slug — drops UUID fragments + 4-char stubs│
│  • Defensive paradigm_slug fallback for Variable nodes            │
└──────────────────────────────────────────────────────────────────┘
      │
      ├─ asyncio.gather ───────────────────────┐
      │                                          │
      ▼                                          ▼
┌──────────────────────────┐    ┌──────────────────────────────────┐
│  populate_kg → Neo4j     │    │  index_stage_output → Qdrant     │
│  • per-node managed tx   │    │  • chunk by stage strategy:      │
│  • MERGE + run_ids accum │    │    researcher: ## sections       │
│  • temporal supersession │    │    formalizer: ### Formulations  │
│  • slug validation       │    │    reasoner:   JSON keys (>4K)   │
│  • ANN sync to           │    │    builder:    code blocks       │
│    kg_entities_dense     │    │  • Voyage embed (batch=128)      │
└──────────────────────────┘    │  • upsert dense + sparse         │
                                 └──────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│  resolver.resolve_and_store                                       │
│  1. _score_importance — Haiku (knowledge_fast_model), 1–10 / fact │
│  2. _find_duplicates — embed_query + memories_dense, cos > 0.85,  │
│                        excludes same run_id                        │
│  3. Branch on best candidate:                                     │
│     • _is_obvious_duplicate (score≥0.95 AND length_ratio<0.10)    │
│       → fast-path DUPLICATE, no Sonnet call                       │
│     • else → _classify_conflict (Sonnet)                          │
│         DUPLICATE      → skip                                     │
│         CORROBORATION  → update_confidence(corroborate)           │
│         ENRICHMENT     → supersede_memory + re-embed merged       │
│         CONTRADICTION  → confidence−0.10 + supersede + meta-mem   │
│  4. New facts → create_memory (Postgres only — Qdrant write       │
│     happens in step 2's index, sharing the same UUID)             │
└──────────────────────────────────────────────────────────────────┘
```

Per-stage namespace + initial confidence:

| Stage | namespace | confidence | memory_type |
|---|---|---|---|
| researcher | paradigm | 0.6 | semantic |
| formalizer | formulation | 0.7 | semantic |
| reasoner | formulation | 0.8 | semantic |
| builder | model | 0.9 | procedural |
| tracker (Phase 2) | simulation | 0.80 | semantic / episodic |

---

## 8. Write path — Tracker (Phase 2, after `observe_simulation`)

`simlab.knowledge.writer.TrackerMemoryWriter` — see `docs/specs/sim-memory/`.

```
Tracker JSON (summary, trajectories[agent_id], episodes[])
      │
      ▼
FactSpec list:
   • 1 fact from summary             (importance=5, semantic)
   • 1 fact per trajectory[agent]    (importance=6, semantic)
   • 1 fact per filtered episode     (importance by type, episodic)
       starvation        → 9
       state_change      → 8
       foraging_failure  → 7
       unknown type      → 6
       foraging_success/exploration/exploitation → DROPPED
      │
      ▼
Single Voyage embed batch
      │
      ▼
Atomic write (same UUID across all 3 stores):
   • shared.memories.create_memory()      → Postgres
   • vector_store.upsert_dense('memories_dense', ...)
   • vector_store.upsert_sparse('memories_sparse', ...)
      │
      ▼
WriteResult{ summaries, trajectories, episodes, skipped_reason? }
```

Confidence fixed at 0.80, run_id=None (Phase 2 has no row in `runs`),
metadata carries the cross-phase join keys (`paradigm`, `formulation`,
`phase1_run_id`, `phase2_experiment_id`, `environment`, `steps`, `seed`).

---

## 9. Read path — `retrieve_knowledge`

Single tool exposed to all Phase 1 agents (and to Phase 2 via the
`retrieve_context` wrapper). Implementation:
`decisionlab/knowledge/retrieval/tool.py:create_retrieve_knowledge`.

```
retrieve_knowledge(query, namespace?, top_k=5, as_of?)
      │
      ▼
asyncio.gather:
   ├─ kg_retrieve         → 2-hop BFS from linked entities,
   │                        score = confidence × 0.85^hops
   └─ vector_retrieve     → dense (Voyage voyage-4-lite query embed)
                            + sparse (BM25 server-side) on
                            artifacts_* AND memories_*
      │
      ▼
fuse_and_rerank
   • RRF (k=60), top 30
   • ZeroEntropy zerank-2 rerank, threshold 0.3, top 10
      │
      ▼
crag.evaluate_results
   • Haiku classifies each → CORRECT | AMBIGUOUS | INCORRECT
   • Routing:
       all CORRECT                      → pass_through
       has AMBIGUOUS                    → web_fallback supplement + rerank
       all INCORRECT                    → full web_fallback
       CORRECT + INCORRECT (no AMBIG)   → keep CORRECT only
   • Fail-closed: grader error → all AMBIGUOUS (logged, surfaces in trace)
      │
      ▼
_apply_recency_weighting
   final_score = score × decay_rate^days_old × confidence_factor
   decay_rate per namespace: paradigm=0.999, formulation=0.998,
                              meta=0.997, model=0.995, simulation=0.99
      │
      ▼
_apply_temporal_filter (when as_of set)
   keep r where created_at ≤ as_of AND (valid_to is null OR valid_to > as_of)
      │
      ▼
_final_truncate
   cap = top_k × 2 if web supplemented else top_k
      │
      ▼
_track_memory_access
   for each Postgres-backed result: touch_memory (+0.02 confidence,
   access_count++, fire-and-forget)
      │
      ▼
Markdown-formatted passages back to caller
```

**Graceful degradation built in at every layer:** missing KG → empty kg_results;
missing vector store → empty vec_results; both missing → "Knowledge backbone
not available". Never raises to the caller.

---

## 10. Consolidation (post-run)

`decisionlab.knowledge.consolidation` runs after the final stage.

1. **Cluster** — load valid memories of this run, embed, pairwise cosine
   matrix (NumPy), single-linkage at threshold 0.80 → clusters of ≥2.
2. **Reflect** — for clusters of ≥3, Haiku generates 1–2 higher-level
   `Reflection` memories (`namespace=meta, memory_type=reflection,
   importance=8.0, confidence=0.7`). Cross-run similarity > 0.85 →
   corroborate the existing reflection.
3. **Time decay** — `apply_time_decay` on non-reflection memories
   inactive ≥30d. Confidences in Qdrant payloads are synced.
4. **Prune** — soft-delete (set `valid_to=now()`) memories with
   `confidence<0.2 AND access_count==0 AND age>90d AND not superseded`.
   Still queryable via `as_of`.

---

## 11. End-to-end data shape across stores

```
                              ┌─────────────────────┐
                              │      MinIO          │
                              │  raw artifacts      │  ← Builder/Tracker write
                              │  (.md, .py, .json,  │
                              │   .pdf, .tex)       │
                              └─────────┬───────────┘
                                        │ s3_key pointer
                                        ▼
   ┌───────────────────────┐   ┌─────────────────────────┐   ┌───────────────────┐
   │      Neo4j            │   │        Postgres         │   │      Qdrant       │
   │                       │   │                         │   │                   │
   │ Paradigm/Variable/    │   │  runs                   │   │ artifacts_dense   │
   │ Equation/BrainRegion/ │◄──┤  models                 │   │ artifacts_sparse  │
   │ Author/Paper/Postulate│   │  experiments            │   │ memories_dense    │
   │ Formulation/Parameter/│   │  artifacts (s3 keys)    │◄──┤ memories_sparse   │
   │ Model/Reflection      │   │  memories (lifecycle)   │   │ kg_entities_dense │
   │ + 11 rel types        │   │                         │   │                   │
   │ + temporal metadata   │   │  same UUID as Qdrant    │   │ same UUID as PG   │
   └───────────┬───────────┘   └─────────────┬───────────┘   └─────────┬─────────┘
               │                              │                         │
               └──────────────┬───────────────┴─────────────────────────┘
                              ▼
                  retrieve_knowledge / retrieve_context
                  (KG 2-hop + dense + sparse → RRF → rerank → CRAG)
```

The **single UUID per memory** ties Postgres rows to Qdrant points. The
`run_ids` array on KG nodes ties them to the run that introduced them.

---

# Last evals — 2026-05-08

Located in `phase1-pablo/evals/reports/`. Latest 6 runs ordered by
timestamp:

| # | Time | Suite (run dir) | Topics | Cost | Verdict |
|---|---|---|---|---|---|
| 1 | 08:20 | baseline-merge-quality | 1 fixture | $0.08 | **FAIL** |
| 2 | 08:30 | phase1-merge-quality | 1 fixture | $0.08 | **FAIL** |
| 3 | 08:44 | phase2-merge-quality | 1 fixture | $0.08 | **FAIL** |
| 4 | 09:32 | cumulative-growth | 5 topics | $4.69 | **FAIL** |
| 5 | 10:39 | phase3-slug-accuracy | 8 topics | $6.23 | **FAIL** |
| 6 | 13:56 | phase4-slug-accuracy | 8 topics | $6.01 | **FAIL** |

All six failed. Three orthogonal issue clusters.

---

## A. Merge precision/recall stuck at F1 = 0.462

Three back-to-back runs of the same fixture (`merge-quality`) all reported
**identical** numbers:

```
n=18  tp=3  fp=0  fn=7  tn=8
precision = 1.000   recall = 0.300   f1 = 0.462
thresholds: P ≥ 0.95   R ≥ 0.90
```

Reading: when the merger says two entities are the same, it is right
(precision 1.000), but it misses 7 of 10 valid merges (recall 0.300).
Three baseline/phase1/phase2 runs producing **bit-identical** numbers
means the "phase" knobs being toggled didn't actually move the merger —
the configuration switch never reaches the merge logic.

## B. Slug canonicalization regressed between phase3 and phase4

The `slug-accuracy` suite asserts the Researcher canonicalizes
"Reinforcement learning" → `reinforcement-learning` (etc.) instead of
minting new slugs. Same 8 topics, same fixture:

| Topic | phase3 (10:39) | phase4 (13:56) |
|---|---|---|
| Q-learning forage | ✓ `reinforcement-learning` | ✗ `exploration-exploitation-trade-off` |
| Loss aversion | ✓ `prospect-theory` | ✓ `prospect-theory` |
| Speed-accuracy DDM | ✓ `drift-diffusion-model` | ✓ `drift-diffusion-model` |
| Bounded rationality | ✗ | ✗ |
| TD(λ) eligibility | ✓ `reinforcement-learning` | ✗ `q-eligibility-traces` |
| DDM collapsing bounds | ✓ `drift-diffusion-model` | ✗ minted new slugs |
| Reference-dependent | ✓ `prospect-theory` | ✓ `prospect-theory` |
| Free-energy principle | ✓ `free-energy-principle` | ✓ `free-energy-principle` |
| **slug_hit_rate** | **7/8 = 0.875 ✓** | **4/8 = 0.500 ✗** |

A real regression in canonicalization between the two runs. KG growth
also blew through limits (`Variable: 7.62/topic, Postulate: 7.75/topic`
in phase3; `Variable: 7.38, Postulate: 6.12` in phase4 — both above the
6/5 ceilings).

## C. `retrieve_knowledge` p95 = ~14–20 s vs 2.5 s budget

| Run | p95 | avg | calls |
|---|---|---|---|
| phase3-slug-accuracy | **19 789 ms** | 16 173 ms | 3 |
| phase4-slug-accuracy | **14 564 ms** | 13 214 ms | 4 |
| paradigm-canonicalization (2026-05-07) | (not asserted) | similar | 38 |

Threshold is 2 500 ms. The tool is **5–8× over budget** at p95. With Haiku
NER + KG 2-hop + parallel dense/sparse + rerank + CRAG-Haiku in series,
this is plausibly LLM latency dominating over retrieval — but no
breakdown is recorded today, so we are guessing where the seconds go.

## D. Cumulative growth: `reinforcement-learning` never minted

The seeding suite (`cumulative-growth`, 2026-05-08 09:32) runs first to
populate the canonical paradigms used downstream by `slug-accuracy`. Its
first topic is "Reinforcement learning in foraging environments" — and
the discovered paradigms were `explore-exploit-tradeoff,
model-based-reinforcement-learning, optimal-foraging-theory`. **The
canonical `reinforcement-learning` slug was not produced**, which is
exactly why phase4-slug-accuracy can't reuse it.

This is the root cause of half the slug-accuracy misses. Fixing
cumulative-growth to consistently emit `reinforcement-learning` and
`bounded-rationality` should propagate through.

---

# Suggested next steps (in priority order)

> Not started. List below is a recommendation; pick what to act on.

### 1. Fix the merge-recall regression first (cheap to debug)

- Reproduce locally: `uv run pytest -k merge_quality` (the fixture is at
  `phase1-pablo/evals/fixtures/`).
- The 3 "phase" runs at 08:20–08:44 produced identical metrics — confirm
  that whatever flag the harness is supposed to flip is actually reaching
  the dedup/merge code path. If the wiring is broken, every "phase" run
  is really the same baseline.
- Inspect the 7 false negatives — likely a single class (e.g. all
  near-duplicate Authors, or all Papers with title vs DOI keys).

### 2. Fix the canonical-paradigm seeding (cumulative-growth)

- Re-run `cumulative-growth` after seeding the KG with canonical slugs
  manually (`reinforcement-learning`, `bounded-rationality`,
  `prospect-theory`, `drift-diffusion-model`, `free-energy-principle`).
- If the Researcher still mints sub-paradigms over the canonical one,
  the issue is the umbrella classifier prompt picking specific theories
  over the parent — lives in `decisionlab/agents/classifier.py` and
  the canonicalization step.
- Re-run `slug-accuracy` immediately after; expect ≥7/8 again.

### 3. Diagnose the regression between phase3 (10:39) and phase4 (13:56)

- Both ran today, on the same fixture, same code base (no commits in that
  window — verify with `git log --since='2026-05-08 10:00' --until='14:00'`).
- If no commits, the regression is **non-deterministic** — likely the LLM
  classifier wandering, or the seeded KG state differing between runs.
- Check `reset_kg_before` in `evals/suites/slug-accuracy.yaml` — it is
  `false`, so phase4 inherited whatever phase3 left in the graph.

### 4. Profile `retrieve_knowledge` to break the 2.5s p95 budget

- Add per-stage timing in `tool.py:handle_retrieve_knowledge` (NER,
  kg_retrieve, vector_retrieve, fuse_and_rerank, CRAG). The aggregate
  number from the eval doesn't tell you which one to attack.
- Likely culprit: CRAG Haiku evaluation is sequential after rerank.
  Either (a) skip CRAG when all fused scores are above a high threshold,
  or (b) parallelize CRAG with the recency weighting / temporal filter.
- Also verify: is the query entity NER call making real Anthropic calls
  even on cached/short queries? If yes, gate it.

### 5. Wire merge-quality numbers into a regression alert

- Three identical FAILs in a row means nobody is acting on this score.
- Either lower thresholds to "block on regression vs. previous run" instead
  of absolute (P=0.95, R=0.90), or fix the recall and keep the bar.
- Either way, add a CI assertion so a silent stay-at-0.300 doesn't ship.

### 6. Lower-priority hygiene

- KG growth caps in slug-accuracy keep being violated (Variable ≥6/topic,
  Postulate ≥5/topic). Once paradigms canonicalize correctly, child-node
  reuse should follow, but worth checking if the Variable composite-id
  fix from `50c952c` actually reduces growth in the next eval.
- Three identical merge-quality reports also mean the eval runner is not
  recording any "phase" metadata — useful to add a `phase` field to the
  JSON so we can tell baseline vs. phase1 vs. phase2 apart from the file
  name alone.

---

---

# Architectural critique — what's structurally wrong

The bug-fix list above gets you green tests. This section is what you'd
rewrite if you were doing the system over today. I read the code, the specs
and the calibration scripts before writing each item — these are not
hypotheticals.

## A1. The merge step exists because identity is solved one layer too late — DONE 2026-05-08

Look at the actual moving parts:

```
canonical-paradigms.json  (slug + name + definition, 18+ entries)
        │
        ├── used by: cli_eval.seed_canonical_paradigms (manual, run once)
        ├── used by: router._pre_anchor (Haiku classifier — run-level)
        └── NOT used by: extract() inside the Memory Agent
                         ↑
                         emits free-text slugs from the stage output
                         ↓
canonicalize.canonicalize() — post-hoc fixup:
   • cosine to existing KG nodes (per-label τ tuned against the same
     fixture the eval grades against)
   • Sonnet verifier when above τ
   • merges into the existing slug or keeps separate
```

The merge-quality F1=0.462 is the metric for that fixup pass. The
`scripts/calibrate_canonicalize_tau.py` already tuned τ against
`canonicalize-pairs.json` — same file as the eval fixture. So you're
optimizing a metric on its own training set and **still** getting 0.300
recall. That's not a tuning problem.

It's a layering problem. The extraction step gives the LLM a free hand to
write any slug it wants ("exploration-exploitation-trade-off",
"q-eligibility-traces"). Downstream, you spend Sonnet calls and a
calibrated cosine threshold trying to recognise that those slugs really
mean "reinforcement-learning". The classifier on the inbound side
(`_pre_anchor`) already knows the canonical slug for the topic. That
information **isn't propagated into the extraction prompt**.

**Refactor.** Make canonical IDs an enum at extraction time:
1. Load `canonical-paradigms.json` at startup and inject `{slug, name,
   definition}` triples into the Researcher / Formalizer / Builder
   extraction prompts as a constrained vocabulary.
2. Force `Paradigm.slug` (and other slug-like labels) to a Pydantic
   `Literal[...]` over the canonical set, with a single `__NEW__` escape
   value for genuinely novel paradigms.
3. When the LLM picks `__NEW__`, run the merge logic. Otherwise, no
   merge step needed.
4. Delete `canonicalize._verify_merge` and the τ calibration script.
   Delete the merge-quality eval suite as the wrong question.

Expected impact:
- The slug-accuracy regression goes away because slugs are picked from
  the controlled list at the point of generation.
- KG growth caps stop being violated because Variables/Postulates can
  inherit the chosen Paradigm's slug as a foreign key.
- One fewer Sonnet call per extracted entity (currently up to one
  per node).
- The `_validate_natural_key` defensive layer (UUID-shape rejection,
  re-slugification, length cap) becomes mostly dead code.

## A2. Two memory systems share one table — leaky abstraction

The `memories` table has columns designed for the Phase 1 lifecycle:
`importance` (LLM-scored), `confidence` (evolves), `corroborations`,
`contradictions`, `superseded_by`, `valid_to`, `last_accessed_at`,
`access_count`. Phase 1 fills all of them.

Phase 2 (`TrackerMemoryWriter`) writes to the same table with:
- `importance` — fixed lookup table by event type
- `confidence` — hard-coded 0.80
- `run_id` — `NULL` (Phase 2 isn't in the `runs` table)
- `corroborations`, `contradictions` — never updated
- The supersession chain — never used
- `valid_to`, `superseded_by` — never set

These are two different ontologies sharing a schema. The shared schema
forces compromises in both directions: Phase 1's `run_id FK` is
nullable because Phase 2 needs to write null; Phase 2 carries the join
keys (`paradigm`, `formulation`, `phase1_run_id`,
`phase2_experiment_id`) inside the JSONB metadata blob because the
schema can't express them.

**Refactor.** Either:
- Split into two tables: `pipeline_memories` (Phase 1 lifecycle) and
  `simulation_observations` (Phase 2 fixed-confidence facts). Both can
  feed the same `memories_dense/sparse` collections via a polymorphic
  Qdrant payload `source_kind` field.
- Or unify properly: make `runs` polymorphic across phases (drop the
  Phase 1-specific columns into a JSONB `phase1_meta`), give Phase 2
  experiments a row in `runs`, and treat the columns as truly shared.

The current state — same table, two semantics, JSONB to paper over
schema gaps — is the worst of both.

## A3. Temporal lifecycle is double-bookkept across Postgres and Neo4j

Both stores carry `valid_from` / `valid_to`. Postgres has it on every
`memories` row; Neo4j has it on every relation (and effectively on every
node via `run_ids` accumulation). They are written by different code
paths at different times for different reasons:

- A new fact arriving at the Memory Agent updates `memories` (PG) via
  `supersede_memory` — but the corresponding `Postulate-[BELONGS_TO]->Paradigm`
  edge in Neo4j gets its own supersession in `populate_kg`, with no
  cross-reference.
- An old `Postulate` fact decays in PG (`apply_time_decay`) but the
  Neo4j edge keeps its original `valid_from` and full confidence.
- Confidence on a `memories` row affects retrieval ranking; the Neo4j
  relation has no `confidence` property at all (it has a different
  notion encoded as `score = confidence_seed * 0.85^hops` *during
  retrieval*, derived nowhere from the actual PG confidence).

There is no "as of T1, what was the world like" query that gives a
consistent answer across PG, Neo4j, and Qdrant. Each store has its own
view of the timeline.

**Refactor.** Pick one store as the source of truth for temporal validity
and replicate from it:
- Source of truth = Postgres `memories` (it's the most expressive).
- Neo4j relations carry only `memory_id` (FK back to PG) + identity
  triple. Drop their `valid_from/valid_to/confidence` properties.
  Temporal queries go: PG filter → set of memory_ids → Neo4j
  pattern match constrained to those ids.
- Qdrant payload mirrors `memory_id` and is rebuilt from PG, never
  written authoritatively.

The "5 stores, 1 UUID" join key already exists; codify it.

## A4. The retrieve path has structural latency, not a tuning problem

p95 = 14–20 s on 2.5 s budget. Counting the LLM round-trips actually
required to answer one query:

1. **Haiku NER** on the query (in `kg_retrieve`) — 1 round-trip.
2. **dense + sparse Qdrant search** — parallel, fast (~100ms).
3. **ZeroEntropy rerank** — 1 external API call (~500ms).
4. **Haiku CRAG grader** on every reranked passage — 1 round-trip.
5. (conditional) **DuckDuckGo web fallback + rerank** when grader emits
   AMBIGUOUS / INCORRECT — extra round-trip + rerank.
6. (conditional) **`touch_memory` writes** for each Postgres-backed result
   — 1 PG round-trip per hit (sequential `for mid in memory_ids`).

Two Haiku calls in series before the agent sees a single character. Even
at 3 s each that's 6 s minimum, before any rerank or web fallback. The
14-20 s observed is plausibly all LLM latency.

The CRAG grader is the most expensive failure-mode amplifier:
- When the grader fails (rate-limit, timeout, schema drift), the
  fail-closed policy marks **every** passage AMBIGUOUS, which triggers
  a web fallback — turning a transient error into a guaranteed slow
  path with two more network calls.
- The reranker (`zerank-2`) already produces a calibrated relevance
  score. CRAG re-evaluates the same thing with a less specialised
  model. The two are doing redundant work.

**Refactor.** Three distinct moves, in order of payoff:

1. **Drop CRAG below a high rerank threshold.** If the top-N rerank
   scores are all ≥ 0.5, skip CRAG entirely. Only call the grader when
   the rerank confidence is low. Estimated cut: ~50% of queries lose
   one Haiku call.

2. **Skip NER for non-named queries.** The current path NER-extracts
   from every query, including "list all paradigms about reward
   learning" where there's no entity to link. Heuristic: skip NER when
   the dense retrieval top-1 score is already above a confidence floor.

3. **Batch `touch_memory`.** It's currently a `for` loop with `await`
   each iteration. Batch into one `UPDATE memories SET ... WHERE id IN (...)`.

Stretch: cache CRAG verdicts by `(query_hash, doc_id)` for repeated
calls within a run — the cumulative-growth eval shows the same agent
re-querying similar things multiple times per topic.

## A5. CRAG fail-closed amplifies LLM outages into web-fallback storms

`crag._classify_results` returns "all AMBIGUOUS" on any error. Routing
treats that as "supplement with web". So **every** retrieve call during a
Haiku outage triggers a DuckDuckGo search + rerank. At 38–43 web calls
per topic in `paradigm-canonicalization`, this is a real cost driver
during transient failures and a noisy-neighbour problem when many topics
run in parallel.

**Refactor.** Distinguish "grader said ambiguous" from "grader couldn't
run". On grader error, return reranked results unchanged with a
`grading_failed=True` marker (the field already exists in
`CRAGResult`, but the routing code ignores it). The marker lets the
agent know the grade is provisional, but doesn't burn a web-fallback
budget.

## A6. Confidence sync between Postgres and Qdrant is half-implemented

- `apply_time_decay` syncs the new confidence to `memories_dense` only.
  `memories_sparse` is **not** synced.
- `update_confidence` (corroboration / contradiction in `shared/memories.py`)
  doesn't sync to Qdrant at all.
- The Qdrant sync that does exist swallows errors at `logger.debug` level.

So the `confidence_factor` used in retrieval recency weighting reads from
Qdrant payload, which can be **out of sync** with PG. Over hundreds of
runs, sparse-channel confidences drift permanently from dense-channel
confidences.

**Refactor.** Either:
- Stop storing confidence on Qdrant payload. Read it from PG at
  retrieval time via a single `WHERE id IN (...)` lookup. Cost: one PG
  round-trip per retrieve. Benefit: single source of truth.
- Or write a single `update_memory_confidence(id, new_conf)` helper
  that updates PG + both Qdrant collections atomically and use it
  everywhere. Audit every write site.

The first is simpler and aligns with A3 (PG as source of truth).

## A7. Module-level singletons in `shared.__init__` are a testing hazard

```python
storage: StorageService | None = None
db: DatabaseService | None = None
kg: KnowledgeGraph | None = None
vectors: VectorStore | None = None
embeddings: EmbeddingService | None = None
sim_memory_writer: object | None = None
```

Every module that wants infra writes `import shared; shared.kg.do_thing()`.
The test seam (`_get_kg`, `_get_vector_store`, `_get_embedding_service`)
exists *because* of this — they're indirection just to support
monkeypatching. Three problems:

1. Multiple test cases in the same process share state: a test that
   calls `init()` leaks a real KG into the next test that wanted a
   mock.
2. Async lifecycle is global. Two concurrent benchmark runs in the same
   process race on `init() / shutdown()`.
3. The `try: from simlab.knowledge import TrackerMemoryWriter` inside
   `_init_sim_memory_writer` creates an import cycle the comment
   itself acknowledges. The Phase 2 layer reaches into Phase 1's
   bootstrap.

**Refactor.** Pass infra through a context object (`AppContext` or
`Services`) constructed once at the entrypoint and threaded down. The
test seams become constructor parameters. The Phase 1 ↔ Phase 2
import cycle becomes a one-way dependency: Phase 2 owns its writer
construction with infra it received, not infra it grabs from a global.

## A8. The Memory Agent's per-stage extraction is tiered (resolved 2026-05-08)

Original critique: `structured.DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"`
and `extraction.extract` called `call_structured(..., model=_STRUCTURED_MODEL)`
unconditionally, while `docs/knowledge-architecture.md` claimed Haiku
("~$0.001 per call"). The eval JSON reports (~30k+30k Sonnet tokens per
topic across resolver+extraction) were consistent with Sonnet, so doc was
wrong by ~10×.

**Resolution (P0-001).** Per-stage tiering replaces the blanket Sonnet
default. Extraction now resolves the model from a `_STAGE_MODELS` dict:

| Stage | Task profile | Model |
|---|---|---|
| Researcher | Filter garbage slugs + scope `paradigm_slug` across nested entities — judgment-heavy | Sonnet 4.6 (`SETTINGS.knowledge_structured_model`) |
| Formalizer | Pull Equation/Variable/Parameter/Formulation from rigid tables | Haiku 4.5 (`SETTINGS.knowledge_fast_model`) |
| Reasoner | Trace `DERIVES_FROM` chains by walking JSON `rules` array | Sonnet 4.6 (`SETTINGS.knowledge_structured_model`) |
| Builder | Extract one Model node + IMPLEMENTS from `.py` + pass/fail — mechanical | Haiku 4.5 (`SETTINGS.knowledge_fast_model`) |
| `resolver._score_importance` | 1–10 rating per fact — mechanical | Haiku 4.5 (`SETTINGS.knowledge_fast_model`) |
| `resolver._classify_conflict` | DUPLICATE / CORROBORATION / ENRICHMENT / CONTRADICTION + write merged content | Sonnet 4.6 (`SETTINGS.knowledge_structured_model`) |

`structured.DEFAULT_MODEL` stays as a back-compat constant for the few
non-extraction call sites still threading it (e.g. `canonicalize.py`,
`agents/researcher.py`'s LLM verifier), but `extraction.extract` and
`resolver` no longer rely on it.

`docs/knowledge-architecture.md` LLM-usage table now reflects this
tiering. Slot defaults are env-overridable via `DECISIONLAB_KNOWLEDGE_FAST_MODEL`
and `DECISIONLAB_KNOWLEDGE_STRUCTURED_MODEL`.

## A9. The Qdrant collection layout duplicates work

Five collections, but two of them (`artifacts_dense`, `artifacts_sparse`)
mirror chunked stage output that is **already on MinIO**. The Memory
Agent writes the chunks to Qdrant during indexing, then never updates
them — a one-shot dump. They have no lifecycle, no supersession, no
confidence evolution. They're a search index over MinIO.

The `kg_entities_dense` collection is a workaround for not having an
entity-vector index in Neo4j proper. Neo4j 5 supports vector indexes
natively. Today we maintain a parallel index in a different store and
manually keep it in sync (best-effort, fire-and-forget — see
`kg_writer.py:457`).

**Refactor.**
- Move `kg_entities_dense` into Neo4j as a native vector index on
  `Paradigm/Variable/Postulate/...` `embedding` properties. One fewer
  store to keep in sync.
- Collapse `artifacts_*` into a single hybrid collection or, better,
  drop them entirely — keep only `memories_*`. Artifacts already exist
  on MinIO and are referenced from the `artifacts` table; if you need
  full-text search over them, an inverted index over the artifact
  records is sufficient. The current design indexes raw stage output
  twice (once at write, never queried by the agent loop the way the
  facts are).

If you keep artifacts indexed, at least give them a TTL — they grow
unboundedly per run with no pruning policy.

## A10. Unbounded `run_ids` array on KG nodes

Every MERGE in `kg_writer._node_work` appends to the node's `run_ids`:

```cypher
ON MATCH SET n += $update_props,
             n.run_ids = coalesce(n.run_ids, []) + $run_id
```

After 100 runs, a popular `Paradigm` (`reinforcement-learning`) carries
a 100-element list. After 1000, it's a 1000-element list serialised on
every read. There is no archival, no rollup ("seen in 47 runs since
2026-04"), no cap.

**Refactor.** Replace the array with a count + last-seen timestamp.
Keep a separate `(node_id, run_id, observed_at)` table in Postgres for
the times you genuinely need the run-by-run history.

## A11. SQLite + Postgres dual experiment registry creates split-brain

`shared/store.py` writes experiments to a local SQLite at
`data/labtfg.db`. `shared/models.py` defines the same `experiments`
table in Postgres. Both are populated by Phase 2. The CLAUDE.md says
"Phase 2 standalone uses SQLite", but the code paths that decide which
to use are not centralised — and the SQLite file walks up the directory
tree looking for `CLAUDE.md` to anchor itself, which silently fails in
deployments without that marker.

**Refactor.** One registry. Postgres is already required for the
memory system; require it for Phase 2 too. Delete `shared/store.py` or
relegate it to a development-mode fallback with a loud warning. Stop
shipping `data/labtfg.db` in the repo.

## A12. The eval harness "phase" knob isn't wired

Three back-to-back runs of `merge-quality.yaml` (baseline, phase1,
phase2) all produced **bit-identical** numbers. The suite YAML file is
the same. The fixture is the same. The Sonnet call (`_verify_merge`)
inside `_merge_precision_recall` doesn't take a "phase" parameter.

The only thing varying between runs is the directory name. Whatever
"phase" was supposed to mean (probably a feature flag toggling some
behaviour in `canonicalize.py`), it never reaches the code under test.
This is also why fixing canonicalize won't move the needle until the
harness is fixed.

**Refactor.** Either thread a real config knob through to
`canonicalize._verify_merge` and assert it's read, or stop running
"phases" until they actually do something. Add a `phase` field to the
report JSON so a future eyeballer can tell three identical reports
apart from their content alone.

## A13. The `slug-accuracy` suite has a non-determinism problem

`reset_kg_before: false` plus running the suite multiple times the same
day with a non-determinic LLM = the second run inherits whatever the
first one left in the graph. Phase3 (10:39, 7/8 hits) seeded the KG
with canonical slugs that phase4 (13:56, 4/8 hits) was supposed to
reuse — but didn't. Either:
- The reuse path is broken (the Researcher doesn't actually consult the
  pre-existing canonical paradigms before minting new ones).
- Or the reuse path *is* working but the LLM still wanders, in which
  case the test is fundamentally noisy.

**Refactor.** Run each eval with a freshly seeded KG containing the
canonical paradigms (no other content), so every run starts from the
same baseline. Variance becomes signal again.

## A14. No retention story anywhere — DONE 2026-05-09 (P3-003)

Cumulative-growth and slug-accuracy run daily, each adding ~500 nodes
and ~200 relations. After a month of CI: 15k nodes, 6k relations, none
of them ever pruned. Postgres `memories` consolidation prunes only
what's `confidence < 0.2 AND access_count == 0 AND age > 90d`, which
biases toward keeping everything. MinIO has no lifecycle policy.
Qdrant has no TTL. The `runs` and `artifacts` tables grow forever.

**Refactor.** Define retention per store:
- MinIO bucket lifecycle: expire artifacts older than N days unless
  marked `keep=true` (e.g. published reports).
- Postgres `runs`: archive or delete eval runs older than N days (the
  fact that `cumulative-growth` runs are visible alongside production
  runs in `memories.run_id` is itself a problem — eval pollution in
  the production table).
- Qdrant `artifacts_*`: TTL or per-run-id cleanup on archival.
- KG `Reflection` nodes from old runs: roll up or drop.

Without this, the eval suite becomes self-defeating: every regression
run leaves more debris behind.

### Retention (resolved by P3-003)

Per-store retention now lives at
[`docs/specs/memory-refactor/retention.md`](specs/memory-refactor/retention.md).
Defaults: `RETENTION_EVAL_DAYS=30`, `RETENTION_PROD_DAYS=365`,
reflection rollup at 90 days.

- **MinIO** — `minio-init` posts a 2-rule lifecycle on boot; `runs/eval/`
  expires after `RETENTION_EVAL_DAYS`, `runs/prod/` after
  `RETENTION_PROD_DAYS`. Verify with `mc ilm export local/labtfg`.
- **Postgres `runs`** — `kind ∈ {prod, eval}` column (default `prod`,
  CHECK constraint). Eval driver tags inserts `kind='eval'`. Prune via
  `uv run cli_eval prune --older-than 30d`; cascades to `memories`,
  `artifacts`, `node_run_observations` via `ON DELETE CASCADE` FKs.
- **Qdrant** — `phase1-pablo/scripts/qdrant_purge_eval.py` reads
  deleted run_ids from the prune output (stdin) and filter-deletes
  matching points across `memories_*` and `artifacts_*` collections.
  The two-step pipe is the prescribed workflow:
  ```bash
  uv run cli_eval prune --older-than 30d \
    | uv run scripts/qdrant_purge_eval.py
  ```
- **KG `Reflection` rollup** — `phase1-pablo/scripts/kg_rollup_reflections.py`
  groups Reflections older than 90d by `YYYY-MM`, MERGEs into
  `RollupReflection` nodes (deduped on re-run), and detach-deletes the
  originals. One transaction per cohort.

`prod`-kind runs and `kg_entities_dense` are intentionally excluded
from automatic retention; see retention.md.

---

## Summary table — what to refactor in what order

| # | Refactor | Effort | Unblocks |
|---|---|---|---|
| **A1** | Canonical IDs at extraction (delete merger) | M | merge-quality, slug-accuracy, KG growth — all 3 root-caused here |
| **A12** | Wire eval phase knob (or delete it) | S | meaningful merge-quality regression detection |
| ~~**A8**~~ | ~~Decide Haiku vs Sonnet for extraction (and document)~~ — done in P0-001 (per-stage tiering) | S | cost predictability, doc/code alignment |
| **A4 + A5** | Make CRAG conditional on rerank confidence + distinguish error from ambiguous | M | retrieve_knowledge p95 ≤ 2.5 s |
| **A6** | Single source of truth for confidence (PG) | M | retrieval ranking accuracy |
| **A2** | Split or unify the memories table | L | clean Phase 1 ↔ Phase 2 boundary |
| **A3** | One temporal lifecycle, replicated read-only | L | "as of T" queries become consistent |
| **A7** | Drop module-level infra singletons | L | testability, parallel runs |
| **A9** | Kill `artifacts_*` collections; move `kg_entities_dense` to Neo4j | M | one fewer store to sync |
| **A10** | Cap `run_ids` accumulation | S | KG node payload size |
| **A13** | Reset KG between eval runs | S | deterministic eval signal |
| **A11** | One experiment registry (Postgres) | S | no split-brain |
| ~~**A14**~~ | ~~Retention policies per store~~ — done in P3-003 | M | system stays sustainable past 6 months |

Effort: S = afternoon, M = a couple of days, L = a week+. None of these
are speculative — every one points at actual code in the current tree.

---

## Files to know

| Concern | File |
|---|---|
| Bootstrap / lifecycle | `shared/shared/__init__.py` |
| Settings + flags | `shared/shared/settings.py` |
| KG schema + ops | `shared/shared/knowledge_graph.py` |
| Vector store + collections | `shared/shared/vector_store.py` |
| Memory lifecycle | `shared/shared/memories.py` |
| ORM models | `shared/shared/models.py` |
| Migrations | `shared/migrations/versions/` |
| Phase 1 extraction | `phase1-pablo/src/decisionlab/knowledge/extraction.py` |
| Phase 1 KG write | `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` |
| Phase 1 indexing | `phase1-pablo/src/decisionlab/knowledge/indexer.py` |
| Phase 1 conflict resolution | `phase1-pablo/src/decisionlab/knowledge/resolver.py` |
| Retrieval entrypoint | `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` |
| CRAG | `phase1-pablo/src/decisionlab/knowledge/retrieval/crag.py` |
| Phase 2 sim writer | `phase2-juan/simlab/knowledge/writer.py` |
| Phase 2 retrieval wrapper | `phase2-juan/simlab/recall/retrieve.py` |
| Latest specs | `docs/specs/{sim-memory,kg-enrichment,sim-recall,knowledge}` |
| Eval reports | `phase1-pablo/evals/reports/2026-05-08-*` |

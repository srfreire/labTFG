# Shared Infrastructure Used by Phase 1

## Purpose

Phase 1 does not embed infrastructure clients inside agents. It receives shared
services through a dependency container and uses them for persistence, artifacts
and memory.

The shared package is not Juan's Phase 2 system. It is repository-level
infrastructure used by both phases.

## Services Container

`shared.services.Services` is the boundary between Phase 1 and infrastructure:

```python
Services(
    db=DatabaseService,
    storage=StorageService,
    kg=KnowledgeGraph | None,
    vectors=VectorStore | None,
    embeddings=EmbeddingService | None,
    sim_memory_writer=None,
)
```

The design replaces module-level globals. Entry points initialize services once
and pass the object down:

```text
CLI / server / eval
  -> init_services()
  -> Router(..., services=services)
  -> agents and tools receive specific services
  -> shutdown_services()
```

## Required vs Optional Services

```text
Required:
  Postgres  -> run/model/artifact metadata and memory lifecycle
  MinIO     -> raw artifact and state storage

Optional:
  Neo4j     -> knowledge graph
  Qdrant    -> vector memory search
  Voyage    -> embeddings
  ZeroEntropy -> reranking
```

If an optional service is unavailable, Phase 1 runs in degraded mode. The core
pipeline can still generate models, but retrieval and memory become limited or
disabled.

## Postgres

Postgres is the durable relational store. Phase 1 uses it for:

- `runs`
- `artifacts`
- `models`
- `pipeline_memories`
- `node_run_observations`

Core tables:

| Table | Phase 1 role |
| --- | --- |
| `runs` | one row per pipeline run, status, report key, memory results |
| `artifacts` | metadata for MinIO objects |
| `models` | approved generated model registry |
| `pipeline_memories` | Phase 1 memory lifecycle and confidence |
| `node_run_observations` | per-run provenance for KG node upserts |

Phase 2-related tables exist in the shared schema, but Phase 1 only needs to
know about `simulation_observations` during retrieval, because retrieved memory
scores can be hydrated from either Phase 1 or Phase 2 memory tables.

## MinIO

MinIO is S3-compatible object storage. It stores the actual artifacts:

```text
research/{run_id}/report.md
research/{run_id}/deep/{slug}.md
research/{run_id}/formulations/{slug}.md
research/{run_id}/env_spec.json
research/{run_id}/pipeline_state.json
research/{run_id}/trace.jsonl

models/{run_id}/reasoner/{paradigm}/{formulation}.json
models/{run_id}/builder/{paradigm}/{formulation}_model.py
models/{run_id}/builder/{paradigm}/test_{formulation}.py
```

The reason for this split is simple:

```text
MinIO: artifact bytes
Postgres: artifact metadata and queryable references
```

This keeps large text/code artifacts out of SQL while preserving relational
metadata for listing, registration and evaluation.

## Neo4j

Neo4j stores scientific graph structure:

```text
(Paper)-[:SUPPORTS]->(Postulate)-[:BELONGS_TO]->(Paradigm)
(Formulation)-[:USES_VARIABLE]->(Variable)
(Model)-[:IMPLEMENTS]->(Formulation)
```

The schema defines allowed labels, unique keys and relation types. It also
creates native vector indexes on selected labels:

```text
Paradigm.embedding
Variable.embedding
Postulate.embedding
Formulation.embedding
Model.embedding
```

These indexes are used for entity linking, replacing an older Qdrant mirror of
KG entities.

Neo4j is not the temporal source of truth. Relations can carry `memory_id`, but
validity windows and confidence are read from Postgres.

## Qdrant

Qdrant stores two collections:

```text
memories_dense
memories_sparse
```

Dense collection:

- Voyage document embeddings
- semantic similarity
- cosine distance
- 1024 dimensions

Sparse collection:

- Qdrant native BM25
- exact/lexical matching
- useful for names, DOIs, symbols and equations

Current design deliberately avoids storing raw artifact chunks in Qdrant. Raw
artifacts live in MinIO. Qdrant receives extracted memory facts.

## Embeddings and Reranking

`EmbeddingService` wraps:

- Voyage AI for embeddings
- ZeroEntropy for reranking

Current roles:

```text
document embedding -> index memory facts and KG entity names
query embedding    -> dense retrieval and ANN entity linking
reranking          -> order fused retrieval results
```

The embedding service is optional. If credentials are missing, retrieval
degrades.

## Agent and LLM Configuration

Phase 1 model settings are loaded from `DECISIONLAB_*` environment variables.
Default roles:

| Slot | Default intent |
| --- | --- |
| Researcher | strong research and synthesis |
| DeepResearcher | focused scientific report generation |
| Formalizer | high-capability mathematical modeling |
| Reasoner | high-capability environment adaptation |
| Builder | code generation with many tool iterations |
| knowledge fast | cheap/mechanical extraction, scoring, CRAG |
| knowledge structured | harder extraction and conflict judgments |
| feedback | review/rerun classification |

The model names use provider-style identifiers, so runtime deployment must be
consistent with the Anthropic/OpenRouter configuration.

## Search Infrastructure

Search is abstracted by `WebSearchPort`. Phase 1 can use:

- Tavily when configured
- DuckDuckGo fallback
- OpenAlex for academic paper search through `search_papers`

The Researcher and DeepResearcher use search heavily. Later stages use stored
artifacts and retrieval more than web search.

## Deployment Shape

The root Docker Compose file provides:

```text
postgres
minio
neo4j
qdrant
phase1-server
phase2-server
web
```

For Phase 1 documentation, the relevant services are Postgres, MinIO, Neo4j,
Qdrant and the Phase 1 server. Phase 2 services are outside this document except
where shared infrastructure is common.

## Important Contracts

```text
Services.db      must be connected before Router persistence.
Services.storage must be connected before agent tools read/write artifacts.
Services.kg      may be None; retrieval and memory degrade.
Services.vectors may be None; vector search/indexing degrade.
Services.embeddings may be None; dense retrieval, reranking and ANN degrade.
```

Qdrant payloads must keep these fields for retrieval:

```text
entity_id
namespace
source_stage
source_kind
run_id
importance
created_at
text_preview
```

Confidence is not trusted from Qdrant payloads. Retrieval fetches live
confidence from Postgres.

## Known Implementation Caveats

These are useful to know when writing the thesis because they mark real system
edges:

- Some old design docs still describe four Qdrant collections. Current code
  uses only `memories_dense` and `memories_sparse`.
- Some old docs describe temporal metadata on Neo4j relations. Current code
  makes Postgres the temporal source of truth and links relations by
  `memory_id`.
- Some migration/maintenance scripts may still expect removed shared globals.
  The runtime path uses `Services`.

## Code Anchors

- Services container: `../shared/shared/services.py`
- Settings: `../shared/shared/settings.py`
- Database service: `../shared/shared/database.py`
- Storage service: `../shared/shared/storage.py`
- ORM models: `../shared/shared/models.py`
- Knowledge graph client: `../shared/shared/knowledge_graph.py`
- Vector store: `../shared/shared/vector_store.py`
- Embedding service: `../shared/shared/embedding.py`
- Pipeline memory helpers: `../shared/shared/pipeline_memories.py`
- Phase 1 config: `src/decisionlab/config.py`
- CLI boot path: `src/decisionlab/cli.py`


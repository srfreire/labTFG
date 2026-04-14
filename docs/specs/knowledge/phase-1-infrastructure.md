# Phase 1: Infrastructure & Storage Layer

> Status: current | Created: 2026-04-14 | Last updated: 2026-04-14

> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Stand up the data layer for the knowledge backbone: Neo4j knowledge graph, Qdrant vector store, Voyage AI embedding/reranking client, Postgres memories table, and Docker Compose wiring. No agents or retrieval logic — just schemas, clients, and infrastructure.

## Requirements

### R1: Neo4j Schema & Async Client
- Neo4j 5.x Docker service with APOC plugin
- Python async client using `neo4j` driver (`AsyncDriver`, `AsyncSession`)
- Node labels: Paradigm, Variable, Equation, BrainRegion, Author, Paper, Postulate, Formulation, Parameter, Model, TestResult — each with uniqueness constraints on natural keys
- Relation types: SUPPORTS, CONTRADICTS, EXTENDS, MEASURES, MODULATES, AUTHORED, DERIVES_FROM, IMPLEMENTS, USES_EQUATION, BELONGS_TO, CITES — all carrying temporal metadata (created_at, run_id, confidence, valid_from, valid_to, superseded_by)
- Indexes on frequently queried properties: slug, doi, name, formulation_id
- Client class `KnowledgeGraph` with methods: `create_node`, `create_relation`, `get_node`, `get_neighbors`, `query` (raw Cypher), `close`
- Connection lifecycle managed via `shared.init()` / `shared.shutdown()`

### R2: Postgres Memories Table
- SQLAlchemy async model `Memory` in `shared/models.py`
- Fields: id (UUID PK), content (text), namespace (enum: paradigm/formulation/model/simulation/meta), memory_type (enum: episodic/semantic/procedural/reflection), source_stage (str), run_id (FK → runs), created_at, updated_at, last_accessed_at, access_count (int, default 0), importance (float, 1-10), confidence (float, 0-1), corroborations (int, default 0), contradictions (int, default 0), valid_from (timestamp), valid_to (timestamp nullable), superseded_by (UUID FK → memories, nullable), metadata (JSONB)
- Table creation via existing init pattern (SQLAlchemy `create_all`)

### R3: Qdrant Collections & Async Client
- Qdrant Docker service (latest stable)
- Python async client using `qdrant-client` (`AsyncQdrantClient`)
- 4 collections: `artifacts_dense` (1024d cosine), `artifacts_sparse` (sparse vectors), `memories_dense` (1024d cosine), `memories_sparse` (sparse vectors)
- Payload schema per point: memory_id/artifact_id, namespace, source_stage, run_id, importance, confidence, created_at
- Client class `VectorStore` with methods: `upsert_dense`, `upsert_sparse`, `search_dense`, `search_sparse`, `delete`, `close`
- Collection creation on init (idempotent — skip if exists)

### R4: Voyage AI Embedding & Rerank Client
- `voyageai` Python SDK
- Wrapper class `EmbeddingService` in `shared/`
- Methods: `embed_texts(texts: list[str]) -> list[list[float]]` (batch, model: `voyage-3`), `embed_query(query: str) -> list[float]`, `rerank(query: str, documents: list[str], top_k: int) -> list[RankedResult]` (model: `rerank-2`)
- `RankedResult` dataclass: index, score, document
- Batching: respect Voyage API limits (128 texts per batch), auto-chunk larger inputs
- Async via `httpx` or Voyage SDK's async support

### R5: Docker Compose & Settings Wiring
- Add `neo4j` and `qdrant` services to existing Docker Compose file
- Neo4j: port 7687 (bolt) + 7474 (browser), volume for data persistence, APOC plugin enabled
- Qdrant: port 6333 (HTTP) + 6334 (gRPC), volume for data persistence
- Environment variables in `shared/settings.py`: NEO4J_URI (default: bolt://localhost:7687), NEO4J_USER (default: neo4j), NEO4J_PASSWORD, QDRANT_URL (default: http://localhost:6333), VOYAGE_API_KEY
- Extend `shared.init()` to connect Neo4j + Qdrant + create schema/collections
- Extend `shared.shutdown()` to close Neo4j + Qdrant connections
- Health check for both services in compose

## Acceptance Criteria

- [x] AC1: `docker compose up` starts Neo4j, Qdrant, Postgres, and MinIO — all healthy within 30 seconds
- [ ] AC2: `shared.init()` connects to all 4 services and creates Neo4j schema + Qdrant collections idempotently
- [x] AC3: Can create a Paradigm node with properties and a SUPPORTS relation between Paper → Postulate via `KnowledgeGraph` client, then query it back
- [ ] AC4: Can insert a Memory row via SQLAlchemy, query by namespace and confidence threshold
- [ ] AC5: Can upsert a dense vector + sparse vector for the same document into Qdrant, then search both and get the document back
- [ ] AC6: Can embed a list of 5 texts via `EmbeddingService` and get 5 vectors of dimension 1024 back
- [ ] AC7: Can rerank 10 documents against a query via `EmbeddingService.rerank()` and get ordered results with scores
- [ ] AC8: Pipeline still works without Neo4j/Qdrant/Voyage (graceful degradation — clients return empty results or raise clear errors caught by callers)
- [x] AC9: All new settings have sensible defaults and are documented in `.env.example`

## Technical Notes

- Follow existing patterns in `shared/storage.py` (async client, init/shutdown lifecycle)
- Follow existing patterns in `shared/models.py` (SQLAlchemy declarative base, UUID PKs)
- `shared/settings.py` uses `pydantic-settings` or `python-dotenv` — match existing pattern
- Neo4j driver: use `neo4j` package with `AsyncGraphDatabase.driver()` — NOT `py2neo` (deprecated)
- Qdrant: use `qdrant-client[async]` for native async support

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Neo4j 5.x over 4.x | 5.x | Native vector index support (future use), better Cypher, APOC included |
| Qdrant sparse vectors over separate BM25 engine | Qdrant native | Single system for both dense+sparse, no Elasticsearch/Tantivy dependency |
| Voyage SDK over raw HTTP | SDK | Handles batching, retries, auth automatically |
| Single `shared/` package for all clients | Yes | Matches existing architecture — `shared` is the infrastructure layer |

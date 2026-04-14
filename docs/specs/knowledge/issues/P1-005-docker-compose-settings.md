---
id: P1-005
title: Extend Docker Compose and shared settings for knowledge infrastructure
status: done
kind: strike
phase: 1
heat: infra
priority: 2
blocked_by: []
created: 2026-04-14
updated: 2026-04-14
---

# P1-005: Extend Docker Compose and shared settings for knowledge infrastructure

## Objective
Add Neo4j and Qdrant services to the existing Docker Compose setup, extend `shared/settings.py` with new environment variables, and wire the new clients into the `shared.init()` / `shared.shutdown()` lifecycle.

## Requirements
- Docker Compose additions:
  - `neo4j` service: image `neo4j:5-community`, ports 7687 (bolt) + 7474 (browser), volume `neo4j_data`, environment for auth (NEO4J_AUTH=neo4j/password), APOC plugin enabled via `NEO4J_PLUGINS=["apoc"]`, healthcheck via `cypher-shell "RETURN 1"`
  - `qdrant` service: image `qdrant/qdrant:latest`, ports 6333 (HTTP) + 6334 (gRPC), volume `qdrant_data`, healthcheck via HTTP GET to `/healthz`
  - Both services on the same Docker network as existing Postgres and MinIO

- Settings additions in `shared/settings.py` (match existing pattern):
  - `NEO4J_URI`: str, default `bolt://localhost:7687`
  - `NEO4J_USER`: str, default `neo4j`
  - `NEO4J_PASSWORD`: str, default `password`
  - `QDRANT_URL`: str, default `http://localhost:6333`
  - `VOYAGE_API_KEY`: str, no default (required when knowledge features are used)

- Lifecycle wiring in `shared/__init__.py` (or wherever `init()`/`shutdown()` live):
  - `init()`: connect Postgres (existing) + MinIO (existing) + Neo4j (`KnowledgeGraph`) + Qdrant (`VectorStore`). Neo4j and Qdrant connections are optional — if env vars are not set or services are unreachable, log a warning and set clients to None. This enables graceful degradation.
  - `shutdown()`: close all connections including Neo4j and Qdrant (if connected)
  - Expose `shared.knowledge_graph` and `shared.vector_store` as module-level references (like existing `shared.storage`)

- `.env.example` updated with all new variables (commented, with descriptions)

## Acceptance Criteria
- [x] AC1: `docker compose up` starts Neo4j, Qdrant, Postgres, and MinIO — all pass health checks
- [x] AC2: `docker compose down -v && docker compose up` starts clean (volumes recreated, schemas re-initialized)
- [x] AC3: `shared.init()` connects to all services when all are available; `shared.knowledge_graph` and `shared.vector_store` are usable after init
- [x] AC4: `shared.init()` succeeds with a warning when Neo4j/Qdrant are unavailable; `shared.knowledge_graph` and `shared.vector_store` are None
- [x] AC5: `shared.shutdown()` closes all connections without error
- [x] AC6: `.env.example` documents all new environment variables
- [x] AC7: Existing pipeline (Researcher → Builder) still works when knowledge services are unavailable (no regressions)

## Files Likely Affected
- `docker-compose.yml` (or `docker-compose.yaml`) — add neo4j + qdrant services
- `shared/shared/settings.py` — add new env vars
- `shared/shared/__init__.py` — extend init/shutdown lifecycle
- `.env.example` — document new variables

## Context
Phase spec: `docs/specs/knowledge/phase-1-infrastructure.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `infra`
Independent of other issues but conceptually should run after P1-001 and P1-003 produce the client classes it wires up. If run in parallel, the wiring can use stubs and be connected once clients exist.

## Completion Summary

**Commit:** `3bf0cf2` — `feat[shared]: add Neo4j + Qdrant infrastructure with graceful degradation (P1-005)`

### What was built
- Neo4j (5-community + APOC) and Qdrant services in Docker Compose with healthchecks, volumes, and env vars passed to phase servers
- Settings: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, QDRANT_URL, VOYAGE_API_KEY added to frozen Settings dataclass
- KnowledgeGraph client stub (neo4j async driver wrapper with connect/close/driver property)
- VectorStore client stub (qdrant-client async wrapper with connect/close/client property)
- shared.init() wires both with graceful degradation — logs warning and sets to None if unreachable
- shared.shutdown() closes all connections including Neo4j and Qdrant
- .env.example documents all new variables
- 7 new tests: graceful degradation (neo4j, qdrant, both), connect success, shutdown cleanup, not-connected guard for both clients

### Files created/modified
- `docker-compose.yml` — added neo4j + qdrant services, volumes, env vars, depends_on
- `shared/shared/settings.py` — 5 new fields (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, QDRANT_URL, VOYAGE_API_KEY)
- `shared/shared/__init__.py` — wired knowledge_graph + vector_store into lifecycle
- `shared/shared/knowledge_graph.py` — new KnowledgeGraph async client
- `shared/shared/vector_store.py` — new VectorStore async client
- `shared/pyproject.toml` — added neo4j>=5.0, qdrant-client>=1.9
- `.env.example` — documented new env vars
- `shared/tests/test_knowledge_lifecycle.py` — 7 new tests
- `shared/tests/test_lifecycle.py` — updated for new singletons
- `shared/tests/test_settings.py` — updated for new settings fields

### Decisions
- Used `wget -qO- http://localhost:7474` for Neo4j healthcheck instead of `cypher-shell` (more reliable during startup, doesn't need auth)
- Used `/readyz` endpoint for Qdrant healthcheck instead of `/healthz` (correct Qdrant endpoint)
- NEO4J_PASSWORD defaults to `labtfg` (matches project convention) instead of `password` from spec
- VOYAGE_API_KEY defaults to empty string instead of raising — required only when knowledge features are used
- Client stubs expose `.driver` / `.client` properties for P1-001 and P1-003 to build on
- Resource leak prevention: connect() methods clean up driver/client on verification failure

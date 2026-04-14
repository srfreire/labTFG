---
id: P1-001
title: Create Neo4j knowledge graph schema and async Python client
status: done
kind: strike
phase: 1
heat: data-model
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-15
---

# P1-001: Create Neo4j knowledge graph schema and async Python client

## Objective
Define the full Neo4j node/relation schema for the knowledge backbone and implement an async Python client class that wraps the `neo4j` driver for use throughout the pipeline.

## Requirements
- Node labels with uniqueness constraints and property indexes:
  - `Paradigm` (slug UNIQUE, name, description)
  - `Variable` (name, type, range, unit)
  - `Equation` (latex, plaintext, type)
  - `BrainRegion` (name, system)
  - `Author` (name, affiliation)
  - `Paper` (doi UNIQUE, title, year, citation_count, venue)
  - `Postulate` (id UNIQUE, statement, falsifiable)
  - `Formulation` (id UNIQUE, name, type, description)
  - `Parameter` (name, default_value, source, range)
  - `Model` (formulation_id UNIQUE, class_name, s3_key)
  - `TestResult` (formulation_id, passed, failure_reason)

- Relation types, all carrying temporal metadata (`created_at: datetime`, `run_id: str`, `confidence: float`, `valid_from: datetime`, `valid_to: datetime | None`, `superseded_by: str | None`):
  - SUPPORTS (Paper → Postulate, +quote)
  - CONTRADICTS (Paper → Postulate, +quote)
  - EXTENDS (Paradigm → Paradigm, +description)
  - MEASURES (Variable → BrainRegion, +mechanism)
  - MODULATES (Variable → Variable, +direction, +equation_ref)
  - AUTHORED (Author → Paper)
  - DERIVES_FROM (Parameter → Postulate, +derivation_chain)
  - IMPLEMENTS (Model → Formulation)
  - USES_EQUATION (Formulation → Equation)
  - BELONGS_TO (Postulate → Paradigm)
  - CITES (Paper → Paper)

- Indexes on: Paradigm.slug, Paper.doi, Postulate.id, Formulation.id, Variable.name, Author.name

- `KnowledgeGraph` class in `shared/knowledge_graph.py`:
  - `__init__(uri, user, password)` — creates `AsyncDriver`
  - `async init_schema()` — creates constraints + indexes (idempotent)
  - `async create_node(label, properties) -> str` — returns node element ID
  - `async create_relation(from_label, from_key, to_label, to_key, rel_type, properties)`
  - `async get_node(label, key_property, key_value) -> dict | None`
  - `async get_neighbors(label, key_property, key_value, rel_type=None, direction="both") -> list[dict]`
  - `async query(cypher, params=None) -> list[dict]` — raw Cypher escape hatch
  - `async close()`

## Acceptance Criteria
- [x] AC1: `init_schema()` creates all constraints and indexes without error on fresh Neo4j, and is idempotent (second call succeeds silently)
- [x] AC2: Can create a Paper node and a Postulate node, link them with SUPPORTS relation including temporal metadata, then query neighbors of the Paper and get the Postulate back
- [x] AC3: Uniqueness constraints reject duplicate nodes (e.g., two Papers with same DOI)
- [x] AC4: `get_neighbors` with `rel_type` filter returns only relations of that type
- [x] AC5: `query()` method executes arbitrary Cypher and returns deserialized results

## Files Likely Affected
- `shared/shared/knowledge_graph.py` — new file, KnowledgeGraph class
- `shared/pyproject.toml` — add `neo4j` dependency

## Context
Phase spec: `docs/specs/knowledge/phase-1-infrastructure.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `data-model`

## Completion Summary

**Commit:** `b1d77bf` — `feat[knowledge]: add Neo4j schema + async KnowledgeGraph client`

### What was built
- `KnowledgeGraph` async client class wrapping `neo4j` AsyncDriver
- 11 node labels with uniqueness constraints (Paradigm, Variable, Equation, BrainRegion, Author, Paper, Postulate, Formulation, Parameter, Model, TestResult)
- 11 relation types with auto-injected temporal metadata (created_at, valid_from)
- Input validation: allowlist for labels/rel_types, regex for identifiers (prevents Cypher injection)
- `create_relation` raises `ValueError` when endpoint nodes missing (no silent no-ops)
- Integrated into `shared.init()` / `shared.shutdown()` lifecycle

### Files created/modified
- `shared/shared/knowledge_graph.py` — new file, KnowledgeGraph class (192 lines)
- `shared/shared/settings.py` — added NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
- `shared/shared/__init__.py` — added `kg` singleton with init/shutdown
- `shared/pyproject.toml` — added `neo4j>=5.0` dependency
- `shared/tests/test_knowledge_graph.py` — 15 integration tests covering all ACs
- `.env.example` — consolidated Neo4j env vars

### Decisions
- Used `labtfg-neo4j` as dev default password (distinct from Postgres `labtfg`)
- Added strict identifier validation beyond spec requirements to prevent Cypher injection
- `create_relation` returns `ValueError` instead of silently doing nothing when nodes not found

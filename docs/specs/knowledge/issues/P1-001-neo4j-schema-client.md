---
id: P1-001
title: Create Neo4j knowledge graph schema and async Python client
status: in-progress
kind: strike
phase: 1
heat: data-model
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-14
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
- [ ] AC1: `init_schema()` creates all constraints and indexes without error on fresh Neo4j, and is idempotent (second call succeeds silently)
- [ ] AC2: Can create a Paper node and a Postulate node, link them with SUPPORTS relation including temporal metadata, then query neighbors of the Paper and get the Postulate back
- [ ] AC3: Uniqueness constraints reject duplicate nodes (e.g., two Papers with same DOI)
- [ ] AC4: `get_neighbors` with `rel_type` filter returns only relations of that type
- [ ] AC5: `query()` method executes arbitrary Cypher and returns deserialized results

## Files Likely Affected
- `shared/shared/knowledge_graph.py` — new file, KnowledgeGraph class
- `shared/pyproject.toml` — add `neo4j` dependency

## Context
Phase spec: `docs/specs/knowledge/phase-1-infrastructure.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `data-model`

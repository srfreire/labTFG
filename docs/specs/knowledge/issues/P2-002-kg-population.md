---
id: P2-002
title: Implement knowledge graph population with node dedup and provenance
status: done
kind: strike
phase: 2
heat: kg-write
priority: 2
blocked_by: [P2-001]
created: 2026-04-14
updated: 2026-04-15
---

# P2-002: Implement knowledge graph population with node dedup and provenance

## Objective
Take an `ExtractionResult` and write its entities and relations to Neo4j, handling deduplication of existing nodes and temporal provenance on all relations.

## Requirements
- Module: `phase1-pablo/src/decisionlab/knowledge/kg_writer.py`

- `async populate_kg(extraction: ExtractionResult, kg: KnowledgeGraph) -> KGWriteResult`
  - Process all nodes, then all relations, in a single Neo4j transaction

- **Node deduplication logic:**
  - For each `NodeSpec`, query Neo4j for existing node with same label + natural_key value
  - If not found: create new node with all properties + `created_at=now`, `run_id`
  - If found: merge properties — new values override old ones, but preserve `created_at` from original. Add `updated_at=now`, append `run_id` to a `run_ids` list property
  - Use Cypher `MERGE` with `ON CREATE SET` / `ON MATCH SET` for atomicity

- **Relation deduplication logic:**
  - For each `RelationSpec`, check if same (from_node, to_node, rel_type) exists with `valid_to=None` (currently valid)
  - If not found: create new relation with `valid_from=now`, `valid_to=None`, `run_id`, `confidence`, other properties
  - If found with same properties (excluding temporal metadata): skip (idempotent)
  - If found with different properties (e.g., different confidence, different quote): mark old relation `valid_to=now`, create new relation with `valid_from=now`. This is the Zep immutable+supersession pattern.

- **Batch execution:** collect all Cypher statements, execute in single transaction. If transaction fails, log error and return partial result (don't crash the pipeline).

- `KGWriteResult` dataclass:
  ```python
  @dataclass
  class KGWriteResult:
      nodes_created: int
      nodes_merged: int
      relations_created: int
      relations_superseded: int
      errors: list[str]
  ```

## Acceptance Criteria
- [x] AC1: Populating from a research ExtractionResult creates all expected nodes (Paradigm, Variables, Papers, etc.) in Neo4j — verifiable via Cypher query
- [x] AC2: Running the same ExtractionResult twice: second run merges nodes (nodes_merged > 0, nodes_created == 0) and skips duplicate relations
- [x] AC3: Running with a modified ExtractionResult (same entities, different relation confidence): old relation gets `valid_to` set, new relation created with `valid_from`
- [x] AC4: All relations carry `run_id`, `created_at`, `confidence`, `valid_from` metadata
- [x] AC5: If Neo4j transaction fails (e.g., constraint violation on unexpected data), the function returns a KGWriteResult with errors populated, not an exception

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` — new file
- `phase1-pablo/src/decisionlab/knowledge/models.py` — add KGWriteResult dataclass

## Context
Phase spec: `docs/specs/knowledge/phase-2-memory-agent.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `kg-write`
Depends on P2-001 for `ExtractionResult` dataclass and extraction output format.
Uses `KnowledgeGraph` client from P1-001.

## Completion Summary

**Commit:** `bb8b54f` — `feat[knowledge]: KG population with node dedup and relation provenance (P2-002)`

### What was built
- `populate_kg()` async function that writes ExtractionResult nodes and relations to Neo4j in a single write transaction
- Node dedup via Cypher MERGE: ON CREATE sets created_at + run_ids, ON MATCH preserves created_at, appends run_id, overrides properties
- Relation dedup with Zep immutable+supersession: checks active (valid_to IS NULL), skips identical, supersedes on property change
- `KGWriteResult` dataclass tracking nodes_created/merged, relations_created/superseded, errors
- Cypher injection prevention: all interpolated identifiers validated against safe-ident regex
- Smart endpoint resolution: node_key_map from current extraction, fallback to schema unique key

### Files created/modified
- `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` — new file, populate_kg() + _resolve_key()
- `phase1-pablo/src/decisionlab/knowledge/models.py` — added KGWriteResult dataclass
- `phase1-pablo/src/decisionlab/knowledge/__init__.py` — exported KGWriteResult and populate_kg
- `shared/shared/knowledge_graph.py` — added unique_key_for() static method and execute_write() method
- `phase1-pablo/tests/knowledge/test_kg_writer.py` — 16 tests covering all 5 ACs plus injection guards and edge cases

### Decisions
- Used node_key_map to resolve relation endpoints by extraction's natural key rather than schema's unique key — handles cases where extraction uses title instead of doi for Papers
- Stripped updated_at from create_props to keep the was_created detection heuristic reliable
- Validated all interpolated Cypher identifiers (labels, rel_type, natural_key) against _SAFE_IDENT regex to prevent injection from LLM-generated extraction data

---
id: P6-001
title: Merge TestResult node into Model node properties
status: done
kind: strike
phase: 6
heat: schema
priority: 3
blocked_by: []
created: 2026-04-16
updated: 2026-04-16
---

# P6-001: Merge TestResult node into Model node properties

## Objective
Remove the `TestResult` node type from the KG schema. Store test outcomes (`passed`, `failure_reason`) as properties on the `Model` node instead. A separate node for a boolean value adds graph complexity without retrieval benefit.

## Requirements

### Remove TestResult from KG schema
- Delete `TestResult` from `_NODE_SCHEMA` in `shared/shared/knowledge_graph.py`
- Remove any relation types that reference TestResult (if any beyond IMPLEMENTS)

### Add test properties to Model node
- Add `passed: bool` and `failure_reason: str|null` to the Model node schema
- Update any MERGE patterns that create Model nodes to include test properties

### Update Builder extraction prompt
- Modify the Builder extraction prompt in `phase1-pablo/src/decisionlab/knowledge/prompts.py`
- Builder should emit test outcomes as properties on Model nodes, not as separate TestResult nodes
- Update the JSON output schema guidance in the prompt

### Update extraction parsing
- Modify `phase1-pablo/src/decisionlab/knowledge/extraction.py` to handle the new Builder output format
- Ensure backward compatibility if old-format extractions are encountered

### Clean up references
- Remove any Cypher queries that reference `:TestResult`
- Update `docs/knowledge-architecture.md` to reflect the change (10 node types instead of 11)
- Update `docs/specs/knowledge/general.md` data model section

## Acceptance Criteria
- [x] No `TestResult` label in `_NODE_SCHEMA`
- [x] Model node has `passed` and `failure_reason` properties
- [x] Builder extraction prompt produces test data as Model properties
- [x] No `:TestResult` in any Cypher query across the codebase
- [x] Existing tests pass
- [x] Architecture docs updated

## Files Likely Affected
- `shared/shared/knowledge_graph.py` — remove TestResult from schema
- `phase1-pablo/src/decisionlab/knowledge/prompts.py` — update Builder prompt
- `phase1-pablo/src/decisionlab/knowledge/extraction.py` — update parsing
- `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` — update if TestResult-specific logic exists
- `docs/knowledge-architecture.md` — update node table (11 → 10 types), update relation table, update Builder extraction row
- `docs/specs/knowledge/general.md` — update data model

## Context
Phase spec: Phase 6 — Schema Cleanse
Heat: `schema`

## Completion Summary

**Commit:** `9c47459` — feat[knowledge]: merge TestResult node into Model properties (P6-001)

### What was built
- Removed `TestResult` from `_NODE_SCHEMA` in `shared/shared/knowledge_graph.py`. KG now has 10 node types.
- Rewrote the Builder extraction prompt so Haiku emits `passed` and `failure_reason` as properties on the Model node and does not produce a standalone TestResult node.
- Added a backward-compat shim `_fold_legacy_test_results` in `extraction.py`. When an old-format payload still contains a TestResult entry, its props are folded onto the matching Model (by `formulation_id`) and the TestResult is discarded. Conflicts with explicit Model values keep the Model's value and log a WARNING; TestResults orphaned from any Model also log a WARNING.
- Updated the Builder response fixture and AC4 assertion in `test_extraction.py`; added 4 new unit tests covering the compat shim edge cases (orphan, missing `formulation_id`, conflict, multi-Model).
- Updated `docs/knowledge-architecture.md` node table (11 → 10) and Builder extraction row. Updated `docs/specs/knowledge/general.md` data model section.
- Removed TestResult entry from `FakeKnowledgeGraph.unique_key_for` in `test_kg_writer.py`.

### Files created/modified
- `shared/shared/knowledge_graph.py` — removed TestResult from `_NODE_SCHEMA`
- `phase1-pablo/src/decisionlab/knowledge/prompts.py` — Builder prompt now emits test outcomes on Model
- `phase1-pablo/src/decisionlab/knowledge/extraction.py` — added `_fold_legacy_test_results` with conflict/orphan logging
- `phase1-pablo/tests/knowledge/test_extraction.py` — updated fixture + AC4, added 4 compat-shim tests
- `phase1-pablo/tests/knowledge/test_kg_writer.py` — dropped TestResult from fake schema
- `docs/knowledge-architecture.md` — node count and Builder row
- `docs/specs/knowledge/general.md` — data model row

### Decisions
- Merge policy for conflicting Model/TestResult values: Model wins (explicit beats inferred), emit a WARNING. Rationale: the new schema treats the Model node as authoritative for its own properties; the compat shim is opportunistic, not overriding.
- Kept TestResult node label absent from `_ALLOWED_LABELS`, so any `TestResult` that reaches `populate_kg` fails fast via `_check_label` — defence-in-depth against stale caches.
- Did not add retrieval indexes on `passed` / `failure_reason`: no current query filters on them.

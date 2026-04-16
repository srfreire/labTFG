---
id: P6-001
title: Merge TestResult node into Model node properties
status: todo
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
- [ ] No `TestResult` label in `_NODE_SCHEMA`
- [ ] Model node has `passed` and `failure_reason` properties
- [ ] Builder extraction prompt produces test data as Model properties
- [ ] No `:TestResult` in any Cypher query across the codebase
- [ ] Existing tests pass
- [ ] Architecture docs updated

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

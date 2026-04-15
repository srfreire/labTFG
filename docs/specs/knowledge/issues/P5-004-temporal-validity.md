---
id: P5-004
title: Add temporal validity queries and historical knowledge access
status: done
kind: strike
phase: 5
heat: consolidation
priority: 4
blocked_by: [P5-001]
created: 2026-04-14
updated: 2026-04-15
---

# P5-004: Add temporal validity queries and historical knowledge access

## Objective
Implement temporal filtering in both Neo4j and Qdrant so the system can answer "what did we know as of run X?" queries, and ensure the immutable+supersession pattern works correctly end-to-end.

## Requirements
- **Neo4j temporal queries:**
  - Add helper method to `KnowledgeGraph`:
    ```python
    async def query_at_time(self, cypher: str, as_of: datetime, params: dict | None = None) -> list[dict]
    ```
    - Wraps Cypher query with temporal filter: only return relations where `valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)`
  - Add helper: `async get_node_history(label, key_property, key_value) -> list[dict]`
    - Returns all versions of a node's relations ordered by `valid_from`, showing how knowledge evolved

- **Postgres temporal queries:**
  - Add to `memories.py`:
    ```python
    async def get_memories_at_time(session, as_of: datetime, namespace=None) -> list[Memory]
    ```
    - Filters: `valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)`
  - Add: `async def get_memory_history(session, content_like: str) -> list[Memory]`
    - Returns a memory and all its superseded predecessors, ordered by `valid_from`

- **Supersession chain traversal:**
  - Given a memory_id, follow `superseded_by` pointers to find the current version
  - Given a current memory, follow reverse `superseded_by` to find all historical versions
  - Utility: `async def get_supersession_chain(session, memory_id) -> list[Memory]`

- **Retrieval temporal mode:**
  - Add optional `as_of: datetime` parameter to `retrieve_knowledge` tool
  - When specified: filter all results to knowledge valid at that point in time
  - Default: None (current knowledge only, `valid_to IS NULL`)

## Acceptance Criteria
- [x] AC1: After 3 runs where a parameter value changed twice (50 → 70 → 65), `get_memory_history` returns all 3 versions in chronological order
- [x] AC2: `query_at_time` with a date between run 1 and run 2 returns the run-1 value (50), not the current value (65)
- [x] AC3: `get_supersession_chain` from the original memory traverses to the current version through all intermediaries
- [x] AC4: `retrieve_knowledge(query, as_of=run_1_date)` returns knowledge as it existed after run 1, excluding knowledge from runs 2 and 3
- [x] AC5: Default retrieval (no `as_of`) returns only currently valid knowledge (valid_to IS NULL)

## Files Likely Affected
- `shared/shared/knowledge_graph.py` — add query_at_time, get_node_history methods
- `shared/shared/memories.py` — add get_memories_at_time, get_memory_history, get_supersession_chain
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — add as_of parameter

## Context
Phase spec: `docs/specs/knowledge/phase-5-cross-run-memory.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `consolidation`
Depends on P5-001 for cross-run retrieval infrastructure being in place.

## Completion Summary

**Commit:** `1f9fd68` — `feat[knowledge]: temporal validity queries and historical knowledge access (P5-004)`

### What was built
- `KnowledgeGraph.query_at_time()`: injects temporal WHERE clause before RETURN in Cypher queries, filtering relations to those valid at a given datetime
- `KnowledgeGraph.get_node_history()`: returns all versions of a node's relations ordered by `valid_from` ascending
- `get_memories_at_time()`: point-in-time Postgres query with `valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)` filtering, timezone-safe
- `get_memory_history()`: LIKE-based content search across all memory versions (including superseded), ordered chronologically
- `get_supersession_chain()`: forward traversal of `superseded_by` pointers with cycle detection and max-depth cap (1000)
- `retrieve_knowledge` tool: new `as_of` ISO8601 parameter; when set, `_apply_temporal_filter` excludes results created after `as_of` or expired before it
- Extracted `_parse_utc` and `_result_created_at` helpers for DRY timestamp handling across recency weighting and temporal filtering

### Files created/modified
- `shared/shared/knowledge_graph.py` — added `query_at_time`, `get_node_history` methods
- `shared/shared/memories.py` — added `get_memories_at_time`, `get_memory_history`, `get_supersession_chain`, `_MAX_CHAIN_LENGTH`
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — added `as_of` to schema, `_apply_temporal_filter`, `_parse_utc`, `_result_created_at`; wired into handler
- `shared/tests/test_knowledge_graph_temporal.py` — 9 tests for KG temporal methods
- `shared/tests/test_memories_temporal.py` — 9 tests for Postgres temporal queries
- `phase1-pablo/tests/knowledge/test_temporal_retrieval.py` — 9 tests for as_of retrieval filtering

### Decisions
- `query_at_time` injects WHERE before RETURN (not WITH after RETURN) to produce valid Cypher
- `get_supersession_chain` has cycle detection (visited set) + 1000-element cap to prevent infinite loops
- `get_memories_at_time` strips tzinfo from `as_of` to match naive TIMESTAMP columns in Postgres
- Unparseable `valid_to` in retrieval results causes exclusion (conservative) rather than silent inclusion
- Temporal filter applied after recency weighting (age-boosted scores are still filtered by validity window)

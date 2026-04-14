---
id: P5-004
title: Add temporal validity queries and historical knowledge access
status: todo
kind: strike
phase: 5
heat: consolidation
priority: 4
blocked_by: [P5-001]
created: 2026-04-14
updated: 2026-04-14
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
- [ ] AC1: After 3 runs where a parameter value changed twice (50 → 70 → 65), `get_memory_history` returns all 3 versions in chronological order
- [ ] AC2: `query_at_time` with a date between run 1 and run 2 returns the run-1 value (50), not the current value (65)
- [ ] AC3: `get_supersession_chain` from the original memory traverses to the current version through all intermediaries
- [ ] AC4: `retrieve_knowledge(query, as_of=run_1_date)` returns knowledge as it existed after run 1, excluding knowledge from runs 2 and 3
- [ ] AC5: Default retrieval (no `as_of`) returns only currently valid knowledge (valid_to IS NULL)

## Files Likely Affected
- `shared/shared/knowledge_graph.py` — add query_at_time, get_node_history methods
- `shared/shared/memories.py` — add get_memories_at_time, get_memory_history, get_supersession_chain
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — add as_of parameter

## Context
Phase spec: `docs/specs/knowledge/phase-5-cross-run-memory.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `consolidation`
Depends on P5-001 for cross-run retrieval infrastructure being in place.

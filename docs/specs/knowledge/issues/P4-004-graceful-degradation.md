---
id: P4-004
title: Implement graceful degradation when knowledge infrastructure is unavailable
status: todo
kind: strike
phase: 4
heat: resilience
priority: 3
blocked_by: [P4-001, P4-003]
created: 2026-04-14
updated: 2026-04-14
---

# P4-004: Implement graceful degradation when knowledge infrastructure is unavailable

## Objective
Ensure the entire pipeline works correctly when Neo4j, Qdrant, or Voyage AI are partially or fully unavailable — no errors, no behavioral changes beyond the absence of knowledge features.

## Requirements
- **Startup degradation** (services not running):
  - `shared.init()` (from P1-005) sets `knowledge_graph`, `vector_store`, `embedding_service` to None when services are unreachable
  - Router detects None and skips Memory Agent + retrieve_knowledge tool creation
  - Log WARNING: "Knowledge infrastructure unavailable: [list of missing services]. Running in degraded mode."

- **Mid-run degradation** (service crashes during pipeline):
  - Memory Agent: catches connection errors in `run()`, returns empty `MemoryAgentResult` with error logged
  - retrieve_knowledge tool: catches connection errors in handler, returns "Knowledge backbone temporarily unavailable. Proceeding without retrieved context."
  - Neither failure blocks the pipeline or causes the agent's agentic loop to error

- **Partial degradation** (some services up, others down):
  - Neo4j down, Qdrant up: KG retrieval skipped, vector retrieval works, Memory Agent skips KG population but still does embedding+indexing
  - Qdrant down, Neo4j up: vector retrieval skipped, KG retrieval works, Memory Agent skips indexing but still does KG population
  - Voyage AI key missing: all embedding operations fail gracefully, fall back to no-knowledge mode

- **Tests**: integration tests that verify each degradation scenario

## Acceptance Criteria
- [ ] AC1: `docker compose up postgres minio` (without neo4j, qdrant) → pipeline runs successfully with degradation warning
- [ ] AC2: Full pipeline run produces identical stage outputs (research reports, formulations, specs, models) in degraded mode vs when knowledge infra was never configured
- [ ] AC3: If Neo4j crashes mid-run (simulate by stopping container), the current Memory Agent call fails gracefully and subsequent stages continue
- [ ] AC4: If Qdrant crashes mid-run, retrieve_knowledge returns the graceful fallback message and the agent continues its loop
- [ ] AC5: Partial degradation (Neo4j up, Qdrant down): KG retrieval still works, Memory Agent still populates KG
- [ ] AC6: No unhandled exceptions in any degradation scenario — all errors are caught and logged

## Files Likely Affected
- `phase1-pablo/src/decisionlab/agents/memory_agent.py` — error handling in run()
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — error handling in handler
- `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py` — connection error handling
- `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py` — connection error handling
- `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` — connection error handling
- `phase1-pablo/src/decisionlab/knowledge/indexer.py` — connection error handling
- `phase1-pablo/tests/` — degradation scenario tests

## Context
Phase spec: `docs/specs/knowledge/phase-4-pipeline-integration.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `resilience`
Depends on P4-001 (tool wiring) and P4-003 (Router hook) being in place to test degradation paths.

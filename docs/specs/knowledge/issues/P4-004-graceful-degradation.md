---
id: P4-004
title: Implement graceful degradation when knowledge infrastructure is unavailable
status: done
kind: strike
phase: 4
heat: resilience
priority: 3
blocked_by: [P4-001, P4-003]
created: 2026-04-14
updated: 2026-04-15
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
- [x] AC1: `docker compose up postgres minio` (without neo4j, qdrant) → pipeline runs successfully with degradation warning
- [x] AC2: Full pipeline run produces identical stage outputs (research reports, formulations, specs, models) in degraded mode vs when knowledge infra was never configured
- [x] AC3: If Neo4j crashes mid-run (simulate by stopping container), the current Memory Agent call fails gracefully and subsequent stages continue
- [x] AC4: If Qdrant crashes mid-run, retrieve_knowledge returns the graceful fallback message and the agent continues its loop
- [x] AC5: Partial degradation (Neo4j up, Qdrant down): KG retrieval still works, Memory Agent still populates KG
- [x] AC6: No unhandled exceptions in any degradation scenario — all errors are caught and logged

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

## Completion Summary

**Commit:** `0f45dd1` — `feat[knowledge]: graceful degradation when knowledge infrastructure is unavailable (P4-004)`

### What was built
- **Startup degradation**: `shared.init()` wraps Neo4j, Qdrant, and Voyage AI initialization in independent try/except blocks — each service fails to None independently without crashing startup. Logs WARNING with list of unavailable services ("Running in degraded mode").
- **Mid-run degradation (tool)**: `handle_retrieve_knowledge` handler wraps the entire retrieval pipeline in try/except — returns "Knowledge backbone temporarily unavailable. Proceeding without retrieved context." on any error, never raises to the agent loop.
- **Mid-run degradation (Memory Agent)**: `MemoryAgent.run()` has a top-level try/except guard that catches all unexpected errors and returns a zeroed `MemoryAgentResult`. The `_emit_status` helper also guards against emit callback failures.
- **Partial degradation (retrieval)**: `kg_retrieve()` catches all exceptions and returns `[]`. `vector_retrieve()` catches all exceptions and returns `([], [])`. The tool handler already had per-channel None checks (falls back to `_noop_kg`/`_noop_vec`).
- **20 integration tests** covering all scenarios: startup (Neo4j down, Qdrant down, Voyage missing, all down, warning logged), mid-run tool (KG crash, Qdrant crash, Voyage crash, never raises), mid-run Memory Agent (crash returns zeroed, never raises, emit failure safe), partial (KG down vector works, Qdrant down KG works, tool partial, Memory Agent partial), no unhandled exceptions (all 4 layers).

### Files created/modified
- `shared/shared/__init__.py` — Added logger, wrapped KG/Qdrant init in try/except, degraded mode warning
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — Wrapped retrieval pipeline in try/except with graceful fallback message
- `phase1-pablo/src/decisionlab/agents/memory_agent.py` — Top-level try/except in `run()`, guarded `_emit_status` helper
- `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py` — `kg_retrieve()` catches all exceptions, returns `[]`
- `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py` — Added logger, `vector_retrieve()` catches all exceptions, returns `([], [])`
- `phase1-pablo/tests/knowledge/test_graceful_degradation.py` — 20 new tests (created)

### Decisions
- `kg_writer.py` and `indexer.py` were not modified because they are already protected by their callers: `populate_kg` has its own try/except, and `index_stage_output` is called via `asyncio.gather(return_exceptions=True)` in `_parallel_write`.
- Guards placed at public API boundaries (`kg_retrieve`, `vector_retrieve`, `handle_retrieve_knowledge`, `MemoryAgent.run`) rather than deep in internal helpers — defense in depth without excessive nesting.
- Pre-existing frozen dataclass mutation bug in `sparse_retrieve` (3 failing tests) was not fixed as it's out of scope for P4-004.

---
id: P1-004
title: Unit and integration tests for KG pre-fetch and agent wiring
status: todo
kind: strike
phase: 1
heat: tests
priority: 3
blocked_by: [P1-002, P1-003]
created: 2026-04-26
updated: 2026-04-26
---

# P1-004: Unit and integration tests for KG pre-fetch and agent wiring

## Objective

Comprehensive test coverage for the prefetch_knowledge function, its
integration with the orchestrator, and the knowledge_context injection
in Analyst and Reporter.

## Requirements

### R1: Unit tests for prefetch_knowledge

All tests mock `retrieve_context` — no real KG needed.

| Test | Verifies |
|------|----------|
| `test_prefetch_analyst_parallel` | Calls retrieve_context twice with correct queries (paradigm + simulation), returns markdown with both subsections |
| `test_prefetch_reporter` | Calls retrieve_context once (meta, top_k=10), returns markdown with References subsection |
| `test_prefetch_partial_failure` | One query raises exception, other succeeds. Returns successful result + calls on_warning |
| `test_prefetch_total_failure` | All queries raise. Returns `""` + calls on_warning |
| `test_prefetch_disabled` | `ENABLE_KNOWLEDGE_READ=False` → returns `""`, retrieve_context never called |
| `test_prefetch_no_paradigm` | `paradigm=""` → returns `""`, retrieve_context never called |

### R2: Unit tests for agent injection

| Test | Verifies |
|------|----------|
| `test_analyst_knowledge_context_injected` | Mock Analyst.run, verify user message contains `## Knowledge context` before `## Tracker observation log` |
| `test_reporter_knowledge_context_injected` | Mock Reporter.run, verify user message contains `## Knowledge context` before `## Tracker observation log` |
| `test_analyst_no_knowledge_context` | `knowledge_context=""` → user message has no `## Knowledge context` section |
| `test_reporter_no_knowledge_context` | `knowledge_context=""` → user message has no `## Knowledge context` section |

### R3: Integration test

| Test | Verifies |
|------|----------|
| `test_prefetch_roundtrip` | With KG fixtures (or mocked retrieve_context returning realistic data), verify full flow: prefetch → format → inject into agent message. Does not require live KG. |

## Acceptance Criteria

- [ ] All 11 tests pass
- [ ] prefetch_knowledge parallel execution verified (analyst stage makes 2 concurrent calls)
- [ ] Warning callback is called on failures
- [ ] No tests require live KG infrastructure
- [ ] Tests follow existing project test patterns (pytest, async)

## Files Likely Affected

- `phase2-juan/tests/test_kg_prefetch.py` — new file with all unit and integration tests

## Context

Phase spec: `docs/specs/kg-enrichment/design.md`
Heat: `tests`

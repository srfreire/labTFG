---
id: P2-002
title: Tests for architect pre-fetch and injection
status: done
kind: strike
phase: 2
heat: tests
priority: 2
blocked_by: [P2-001]
created: 2026-04-26
updated: 2026-04-26
---

# P2-002: Tests for architect pre-fetch and injection

## Objective

Add tests for the architect stage in prefetch_knowledge and the
knowledge_context injection in Architect.run().

## Requirements

### R1: Unit tests for architect prefetch

| Test | Verifies |
|------|----------|
| `test_prefetch_architect` | Calls retrieve_context twice (paradigm + simulation), returns markdown |

### R2: Unit tests for architect injection

| Test | Verifies |
|------|----------|
| `test_architect_knowledge_context_injected` | User message includes knowledge context after prompt |
| `test_architect_no_knowledge_context` | No context → message identical to before |

## Acceptance Criteria

- [ ] All 3 new tests pass
- [ ] Full suite passes with no regressions

## Files Likely Affected

- `phase2-juan/tests/test_kg_prefetch.py` — add architect tests

## Context

Phase spec: `docs/specs/kg-enrichment/design.md`
Heat: `tests`

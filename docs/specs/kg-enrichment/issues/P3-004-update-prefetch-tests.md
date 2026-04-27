---
id: P3-004
title: Update prefetch tests for new formulation queries
status: done
kind: strike
phase: 3
heat: tests
blocked_by: [P3-001, P3-002, P3-003]
---

# P3-004: Update prefetch tests for new formulation queries

## What

Update existing tests in `tests/test_kg_prefetch.py` to account for the new
formulation queries:

- `test_prefetch_analyst_parallel`: assert 3 queries (was 2), verify "Formulations" subsection
- `test_prefetch_reporter`: assert 2 queries (was 1), verify "Formulations" subsection
- `test_prefetch_partial_failure`: adapt for 3-query analyst scenario
- `test_analyst_knowledge_context_injected`: verify formulations in user message
- `test_reporter_knowledge_context_injected`: verify formulations in user message

## Why

Existing tests assert specific query counts and section names. Adding formulation
queries changes these expectations.

## Acceptance criteria

- All existing prefetch tests pass with updated assertions
- No new test files needed — changes fit existing structure
- Tests verify both happy path (formulation content present) and empty path (no formulation results)

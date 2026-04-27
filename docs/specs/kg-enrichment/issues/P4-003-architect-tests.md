---
id: P4-003
title: Update architect prefetch tests for formulation query
status: done
kind: strike
phase: 4
heat: tests
blocked_by: [P4-001, P4-002]
---

# P4-003: Update architect prefetch tests for formulation query

## What

Update `test_prefetch_architect` in `tests/test_kg_prefetch.py` to assert 3 queries (was 2) and verify "Formulations" subsection.

## Acceptance criteria

- `test_prefetch_architect` passes with 3-query side_effect
- All 15+ tests still pass

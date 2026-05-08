---
id: P1-003
title: Route __NEW__ slugs through canonicalize._verify_merge, skip otherwise
status: todo
kind: strike
phase: 1
heat: extraction
priority: 1
blocked_by: [P1-002]
created: 2026-05-08
updated: 2026-05-08
---

# P1-003: Conditional canonicalize on __NEW__ only

## Objective

Stop calling `canonicalize._verify_merge` on every extraction. Only
invoke it when at least one node carries `slug == "__NEW__"` —
canonical-slug nodes go straight to `populate_kg` without a Sonnet
call.

## Requirements

Per phase spec R3:

1. In `decisionlab/agents/memory_agent.py`, replace the unconditional
   `extraction = await canonicalize(extraction, ...)` with:
   ```python
   needs_canon = any(
       n.label in CANONICALIZE_LABELS
       and n.properties.get("slug") == "__NEW__"
       for n in extraction.nodes
   )
   if needs_canon:
       extraction = await canonicalize(extraction, ...)
   ```
2. The skipped-path codepath must not log a warning — it's the new
   normal. Add an INFO log only on the run path.
3. Add a unit test that a fully-canonical extraction does not invoke
   `canonicalize` (mock the function; assert call count = 0).
4. Add a unit test that an extraction containing a single `__NEW__`
   node DOES invoke `canonicalize`.

## Acceptance Criteria

- [ ] AC1: Skip-path: `canonicalize` is not called when no `__NEW__`
      slug appears. Test asserts mock call count = 0.
- [ ] AC2: Run-path: `canonicalize` is called when any node carries
      `slug=="__NEW__"`. Test asserts mock call count = 1.
- [ ] AC3: Cumulative-growth eval still passes — the bootstrap topic
      "Reinforcement learning in foraging environments" emits
      `__NEW__` for sub-paradigms (or canonical for the main one);
      verify the merger correctly resolves what the LLM emits.
- [ ] AC4: Slug-accuracy eval (with P0-003 reset+seed and P1-001/002
      already in place) shows a measurable drop in `_verify_merge`
      Sonnet calls — at least 50 % reduction vs the
      `2026-05-08-phase4-slug-accuracy` baseline.
- [ ] AC5: Memory-agent integration test confirms the conditional
      path; both branches exercised.

## Files Likely Affected

- `phase1-pablo/src/decisionlab/agents/memory_agent.py` —
  conditional canonicalize call.
- `phase1-pablo/tests/agents/test_memory_agent.py` (or equivalent) —
  cover both branches.

## Context

Phase spec: `docs/specs/memory-refactor/phase-1-canonical-ids.md` (R3)
Heat: `extraction` (depends on P1-002)

---
id: P3-001
title: Unify all confidence write sites through one atomic helper
status: done
kind: strike
phase: 3
heat: confidence
priority: 1
blocked_by: [P2-004]
created: 2026-05-08
updated: 2026-05-09
---

# P3-001: Single confidence-write helper

## Objective

Stop the silent drift across confidence write sites. Today
`apply_time_decay` syncs only `memories_dense` (sparse drifts);
`update_confidence` syncs neither store. Add an atomic helper that
applies the change to Postgres in one `UPDATE ... RETURNING`,
clamps to [0.1, 1.0], and returns the new value. Refactor every
caller through it.

This issue does **not** drop the Qdrant `confidence` field —
that's P3-002. P3-001's goal is just to consolidate the writes so
the next step has a single line to change.

## Requirements

Per phase spec R1:

1. Add to `shared/shared/memories.py`:
   ```python
   async def update_memory_confidence(
       session: AsyncSession,
       memory_id: uuid.UUID,
       *,
       delta: float | None = None,
       set_to: float | None = None,
   ) -> float:
       """Apply a confidence change atomically, clamp, and return the
       new value. Exactly one of delta / set_to must be provided."""
   ```
   Clamp to `[_CONFIDENCE_FLOOR, _CONFIDENCE_CAP]`.
2. Refactor every confidence-write site to use the helper:
   - `touch_memory` — uses `delta=+0.02`.
   - `update_confidence(corroborate=True)` — `delta=+0.05`.
   - `update_confidence(contradict=True)` — `delta=-0.10`.
   - `apply_time_decay` — per-row `set_to=new_value`.
3. Remove the inline `func.least` / `func.greatest` clamp expressions
   from each caller; the helper owns clamping.
4. Add unit tests covering: clamp at upper, clamp at lower, +delta,
   −delta, set_to, set_to-out-of-range.

## Acceptance Criteria

- [x] AC1: `update_memory_confidence` exists with atomic
      `UPDATE ... RETURNING` and exact clamp boundaries.
- [x] AC2: All four call sites (`touch_memory`,
      `update_confidence` corroborate/contradict, `apply_time_decay`,
      and the resolver enrichment path) route through the helper.
      `grep -rn 'Memory.confidence + ' shared/ phase1-pablo/`
      returns no inline expressions outside the helper itself.
- [x] AC3: Unit tests cover all clamp paths and both `delta` and
      `set_to` modes.
- [x] AC4: Existing memory-decay and corroboration integration tests
      still pass with no behavioural change.
- [x] AC5: A confidence write succeeds atomically — concurrent
      corroborations on the same memory ID converge to the correct
      total (test via `asyncio.gather`).

## Files Likely Affected

- `shared/shared/memories.py` — add helper, refactor `touch_memory`,
  `update_confidence`, `apply_time_decay`.
- `phase1-pablo/src/decisionlab/knowledge/resolver.py` — enrichment
  path uses helper.
- `phase1-pablo/src/decisionlab/knowledge/consolidation.py` — decay
  path uses helper.
- `shared/tests/test_memories.py` — clamp + concurrency tests.

## Context

Phase spec: `docs/specs/memory-refactor/phase-3-data-integrity.md` (R1)
Heat: `confidence`

## Completion Summary

**Commit:** `d260cc6` — `feat[knowledge]: unify confidence writes through update_memory_confidence (P3-001)`

### What was built
- New `shared.memories.update_memory_confidence(session, id, *, delta, set_to) -> float` issuing one `UPDATE ... RETURNING confidence`, clamped server-side via `func.least(1.0, func.greatest(0.1, ...))`.
- `touch_memory`, `update_confidence` (corroborate / contradict), and `apply_time_decay` all delegate to the helper. Inline `func.least`/`func.greatest` clamps are gone from each caller. Resolver enrichment / contradiction and consolidation reflection-corroboration go through `update_confidence`, so they pick up the helper transitively.
- `grep -rn 'Memory.confidence + ' shared/ phase1-pablo/` returns one match: the helper itself.
- Unit tests for delta±, set_to, set_to-out-of-range, both clamp boundaries, exactly-one-of validation, and concurrent corroborations via `asyncio.gather` (5 sessions × +0.05 from 0.5 → 0.75).
- Confidence-evolution mock tests rewritten to assert `update_memory_confidence` is awaited with the expected arguments instead of inspecting compiled SQL — keeps clamp/delta semantics in one place.

### Files created/modified
- `shared/shared/memories.py` — added helper; refactored `touch_memory`, `update_confidence`, `apply_time_decay` to route through it.
- `shared/tests/test_memories.py` — added 8 helper tests (+ concurrent corroboration test).
- `phase1-pablo/tests/knowledge/test_confidence_evolution.py` — rewrote AC1/AC2/AC3/AC6 tests against the helper instead of compiled SQL.
- `phase1-pablo/tests/knowledge/test_retrieval_tool.py` — patched `update_memory_confidence` in the two `_track_memory_access` tests so they keep asserting one batched UPDATE + one commit.

### Decisions
- Did not drop the Qdrant `confidence` field — explicitly out of scope for P3-001 (P3-002).
- Two-statement transaction in `update_confidence` (counter UPDATE then helper) accepted: both run inside the caller's session before commit, so a partial failure rolls back together.
- Concurrent test uses the spec-mandated `asyncio.gather` shape; convergence to 0.75 confirms atomicity at the DB layer (READ COMMITTED + row lock on `UPDATE ... SET confidence = LEAST/GREATEST(... + delta)`).

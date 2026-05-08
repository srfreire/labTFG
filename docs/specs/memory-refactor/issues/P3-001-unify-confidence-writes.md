---
id: P3-001
title: Unify all confidence write sites through one atomic helper
status: in-progress
kind: strike
phase: 3
heat: confidence
priority: 1
blocked_by: [P2-004]
created: 2026-05-08
updated: 2026-05-08
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

- [ ] AC1: `update_memory_confidence` exists with atomic
      `UPDATE ... RETURNING` and exact clamp boundaries.
- [ ] AC2: All four call sites (`touch_memory`,
      `update_confidence` corroborate/contradict, `apply_time_decay`,
      and the resolver enrichment path) route through the helper.
      `grep -rn 'Memory.confidence + ' shared/ phase1-pablo/`
      returns no inline expressions outside the helper itself.
- [ ] AC3: Unit tests cover all clamp paths and both `delta` and
      `set_to` modes.
- [ ] AC4: Existing memory-decay and corroboration integration tests
      still pass with no behavioural change.
- [ ] AC5: A confidence write succeeds atomically — concurrent
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

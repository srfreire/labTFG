---
id: P2-003
title: Batch touch_memory writes into a single UPDATE per retrieve
status: in-progress
kind: strike
phase: 2
heat: db-batching
priority: 2
blocked_by: [P1-004]
created: 2026-05-08
updated: 2026-05-08
---

# P2-003: Batch memory access updates

## Objective

Replace the per-id `for mid in memory_ids` loop in
`_track_memory_access` with one batched `UPDATE ... WHERE id IN (...)`.
Removes N round-trips per retrieve.

## Requirements

Per phase spec R3:

1. In `decisionlab/knowledge/retrieval/tool.py:_track_memory_access`,
   replace the iteration with:
   ```python
   await session.execute(
       update(Memory)
       .where(Memory.id.in_(memory_ids))
       .values(
           last_accessed_at=func.now(),
           access_count=Memory.access_count + 1,
           confidence=func.least(1.0, Memory.confidence + 0.02),
       )
   )
   await session.commit()
   ```
2. Keep the fire-and-forget try/except wrapping at the call site
   (`retrieve_knowledge` shouldn't fail because `touch_memory`
   failed).
3. Update the existing `touch_memory` helper to optionally accept a
   list (for callers that already have multiple ids); per-id callers
   still work.

## Acceptance Criteria

- [ ] AC1: `_track_memory_access` issues one SQL statement per call
      regardless of `len(memory_ids)`. Test asserts via mocked
      session: exactly one `execute` + one `commit`.
- [ ] AC2: Confidence clamp is preserved (capped at 1.0); existing
      decay/access tests still pass.
- [ ] AC3: Per-id `touch_memory` callers (if any remain) continue to
      work.
- [ ] AC4: Telemetry: log `touch_memory.batch_size` per call.
- [ ] AC5: Integration test confirms `access_count` increments by 1
      per id, `last_accessed_at` updated, `confidence` boosted by
      0.02 (capped) — same observable behaviour as before, fewer
      round-trips.

## Files Likely Affected

- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` —
  `_track_memory_access` rewrite.
- `shared/shared/memories.py` — optionally extend `touch_memory` to
  accept a list.
- `phase1-pablo/tests/knowledge/retrieval/test_tool.py` — assertion
  on call count.

## Context

Phase spec: `docs/specs/memory-refactor/phase-2-retrieve-latency.md` (R3)
Heat: `db-batching` (independent of P2-001 / P2-002 / P2-004)

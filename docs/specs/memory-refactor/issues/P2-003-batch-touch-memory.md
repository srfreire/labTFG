---
id: P2-003
title: Batch touch_memory writes into a single UPDATE per retrieve
status: done
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

- [x] AC1: `_track_memory_access` issues one SQL statement per call
      regardless of `len(memory_ids)`. Test asserts via mocked
      session: exactly one `execute` + one `commit`.
- [x] AC2: Confidence clamp is preserved (capped at 1.0); existing
      decay/access tests still pass.
- [x] AC3: Per-id `touch_memory` callers (if any remain) continue to
      work.
- [x] AC4: Telemetry: log `touch_memory.batch_size` per call.
- [x] AC5: Integration test confirms `access_count` increments by 1
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

## Completion Summary

**Commit:** `758b6ab` — `feat[knowledge]: batch touch_memory writes into a single UPDATE (P2-003)`

### What was built
- `_track_memory_access` now collects all Postgres-backed `entity_id`s
  and hands them to a single batched `touch_memory(session, [...])`
  call followed by one `await session.commit()`. The previous per-id
  `for mid in memory_ids` loop (N round-trips, N flushes) is gone.
- `shared.memories.touch_memory` now accepts either a single
  `uuid.UUID` or any `Iterable[uuid.UUID]` — single-id callers
  (`tests/test_memories.py:test_ac6_touch_memory`,
  `phase1-pablo/tests/knowledge/test_confidence_evolution.py`'s
  AC3 confidence-cap tests) keep working untouched. The SQL is the
  same shape in both cases (`UPDATE ... WHERE id IN (...)`), and the
  `func.least(1.0, Memory.confidence + 0.02)` clamp is preserved.
- Helper returns the number of ids targeted (0 for empty input → no
  SQL is sent, the callers' fire-and-forget wrapping in
  `_track_memory_access` and the `try/except` log around it both
  remain).
- Telemetry: `_track_memory_access` emits a
  `touch_memory.batch_size=<N>` INFO log on each successful batched
  write — proves at runtime that batching landed and lets us watch
  batch sizes evolve as result counts shift.

### Files created/modified
- `shared/shared/memories.py` — `touch_memory` signature widened to
  `uuid.UUID | Iterable[uuid.UUID]`, body collapses to one batched
  `UPDATE ... WHERE id IN (...)`. Returns `int` (count of ids
  targeted) instead of `None`; existing callers discard the return
  value, no behaviour change.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` —
  `_track_memory_access` replaced with a single batched call +
  commit, `try/except` now wraps the whole batch (logs
  `touch_memory failed for batch of N`), and the success path emits
  `touch_memory.batch_size=N`.
- `phase1-pablo/tests/knowledge/test_retrieval_tool.py` —
  `TestAC7_MemoryAccessTracking` updated to assert the batched call
  shape (list of UUIDs passed positionally) and grew three new
  tests: AC1 (one execute + one commit on the mocked session), AC4
  (`touch_memory.batch_size=3` log captured via caplog), and a no-op
  guard (no execute/commit when there are no memory-backed hits).
- `shared/tests/test_memories.py` —
  `test_touch_memory_batch_updates_each_id` integration test
  (Postgres-backed) creates three rows at confidences 0.5 / 0.99 /
  1.0, runs `touch_memory(session, [a, b, c])`, and asserts
  access_count == 1, last_accessed_at populated, and the +0.02
  confidence boost is clamped at 1.0 for the 0.99 and 1.0 rows.
  `test_touch_memory_empty_list_is_noop` covers the empty-input
  short-circuit.

### Decisions
- **`touch_memory` returns `int`** instead of `None`. The spec didn't
  require a return value, but it's the cheapest way to expose batch
  size to callers that want to log it (and at the empty-input path
  it's the natural way to say "did nothing"). Existing single-id
  callers don't read the return, so backwards-compatible.
- **Telemetry log lives in `_track_memory_access`**, not in
  `touch_memory` itself. The helper is generic; the
  `touch_memory.batch_size` counter is specifically about retrieve
  hot-path behaviour. Putting it in the caller keeps the helper
  focused and avoids polluting per-id callers' logs.
- **Wrap the whole batch in one `try/except`** rather than per-id
  fallback. The previous loop's per-id `try/except` caught
  individual failures, but with one batched UPDATE there is no
  meaningful per-id distinction — the statement either lands or it
  doesn't. The fire-and-forget contract at the call site
  (`retrieve_knowledge` shouldn't fail because tracking failed) is
  preserved by the outer `try/except` in
  `handle_retrieve_knowledge` and now also a defensive `return`
  inside the batched try.

---
id: P1-003
title: Route __NEW__ slugs through canonicalize._verify_merge, skip otherwise
status: done
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

- [x] AC1: Skip-path: `canonicalize` is not called when no `__NEW__`
      slug appears. Test asserts mock call count = 0.
- [x] AC2: Run-path: `canonicalize` is called when any node carries
      `slug=="__NEW__"`. Test asserts mock call count = 1.
- [ ] AC3: Cumulative-growth eval still passes — the bootstrap topic
      "Reinforcement learning in foraging environments" emits
      `__NEW__` for sub-paradigms (or canonical for the main one);
      verify the merger correctly resolves what the LLM emits.
      *(deferred — eval-driven, runs alongside P1-004)*
- [ ] AC4: Slug-accuracy eval (with P0-003 reset+seed and P1-001/002
      already in place) shows a measurable drop in `_verify_merge`
      Sonnet calls — at least 50 % reduction vs the
      `2026-05-08-phase4-slug-accuracy` baseline.
      *(deferred — eval-driven, runs alongside P1-004)*
- [x] AC5: Memory-agent integration test confirms the conditional
      path; both branches exercised.

## Files Likely Affected

- `phase1-pablo/src/decisionlab/agents/memory_agent.py` —
  conditional canonicalize call.
- `phase1-pablo/tests/agents/test_memory_agent.py` (or equivalent) —
  cover both branches.

## Context

Phase spec: `docs/specs/memory-refactor/phase-1-canonical-ids.md` (R3)
Heat: `extraction` (depends on P1-002)

## Completion Summary

**Commit:** `3bf0024` — `feat[knowledge]: route only __NEW__ extractions through canonicalize (P1-003)`

### What was built
- Imported `CANONICALIZE_LABELS` alongside `canonicalize` in
  `agents/memory_agent.py` and wrapped the previous unconditional
  `await canonicalize(...)` block in a `needs_canon` guard:
  ```python
  needs_canon = any(
      n.label in CANONICALIZE_LABELS
      and n.properties.get("slug") == "__NEW__"
      for n in extraction.nodes
  )
  ```
  When the gate is `False`, the extraction flows straight to
  `populate_kg` — no Sonnet `_verify_merge` call, no warning log
  (skip-path is the new normal).
- Run-path emits a single `logger.info` line (`"__NEW__ slug detected
  for stage=… — routing extraction through canonicalize"`) so
  observability still distinguishes the two branches without flooding
  the canonical-only path.
- Existing `try/except` around the `canonicalize` call is preserved
  inside the gated block, so failures still degrade silently to the
  un-canonicalized extraction.
- Three new test cases in
  `tests/knowledge/test_memory_agent.py`:
  - `test_canonicalize_skipped_when_no_new_slug` — fully-canonical
    extraction (`reinforcement-learning` + `prospect-theory`) asserts
    `m_canon.call_count == 0`. **AC1**.
  - `test_canonicalize_runs_when_new_slug_present` — extraction with a
    single `__NEW__` Paradigm asserts `m_canon.call_count == 1`. **AC2**.
  - `test_canonicalize_skipped_when_only_non_canonicalize_labels` —
    `slug="__NEW__"` on a `Paper` node (outside `CANONICALIZE_LABELS`)
    must not trigger the gate.
  All three are mocked unit tests at the `MemoryAgent.run` boundary,
  satisfying **AC5** (both branches exercised).
- New `_patch_canonicalize` helper echoes the input extraction through
  `AsyncMock` `side_effect` so the gate check reads `call_count`
  without disturbing the rest of the pipeline.

### Decisions
- **AC3 / AC4 deferred** — both are eval-driven (cumulative-growth and
  slug-accuracy YAML eval suites against real LLM extractions). They
  validate behavior across the full P1 chain, not the gate in
  isolation, and are best run as a single regression once P1-004
  deletes the merger. Marked deferred rather than completed; the gate
  itself is fully covered by unit tests.
- **No edit to `test_run_calls_all_subsystems` docstring** — reviewer
  flagged that its `AC1/AC2` label collides with P1-003's ACs, but
  those refer to the test file's own historic conventions (likely the
  parent `MemoryAgent` epic), not to this issue. Kept as-is rather
  than retro-relabel an unrelated test.

### Files created/modified
- `phase1-pablo/src/decisionlab/agents/memory_agent.py` — added
  `CANONICALIZE_LABELS` import; wrapped `canonicalize` call in
  `needs_canon` gate with INFO log on the run path.
- `phase1-pablo/tests/knowledge/test_memory_agent.py` — added
  `_patch_canonicalize` helper, `_extraction_with_slugs` fixture, and
  three test cases covering AC1/AC2/AC5.

---
id: P2-004
title: Distinguish CRAG grader errors from genuine AMBIGUOUS verdicts
status: done
kind: strike
phase: 2
heat: crag-grader
priority: 2
blocked_by: [P2-001]
created: 2026-05-08
updated: 2026-05-08
---

# P2-004: Don't web-fallback on grader errors

## Objective

When the CRAG Haiku grader fails (rate-limit, timeout, schema drift),
today's routing treats every passage as AMBIGUOUS, which forces a
DuckDuckGo web fallback. During Haiku outages this turns every
retrieve into a 2-network-hop slow path. The `grading_failed` flag
already exists on `CRAGResult`; the routing code just ignores it.

## Requirements

Per phase spec R4:

1. In `decisionlab/knowledge/retrieval/crag.py:evaluate_results`,
   before the routing logic, check `grading_failed`:
   ```python
   if grading_failed:
       return CRAGResult(
           results=results,
           action="grader_unavailable",
           evaluations=evaluations,
           web_results_used=0,
           grading_failed=True,
       )
   ```
   Skip the web-fallback paths entirely on this branch.
2. In `tool.py`, add `[grader_unavailable]` to the formatted output
   header so the agent can see the grade is provisional.
3. Telemetry counter: `crag.grader_failed`.
4. Add a unit test that simulates a grader error
   (`_classify_results` returns the fail-closed sentinel) and asserts
   `web_results_used == 0` and the action is `grader_unavailable`.

## Acceptance Criteria

- [ ] AC1: When grader fails, `evaluate_results` returns immediately
      with `action="grader_unavailable"` and zero web calls.
- [ ] AC2: Output formatting includes a visible
      `[grader_unavailable]` marker; agents can read it.
- [ ] AC3: Telemetry records grader failures.
- [ ] AC4: Existing CRAG tests (genuine AMBIGUOUS, all CORRECT, mixed)
      still pass.
- [ ] AC5: A simulated Haiku rate-limit run shows zero
      DuckDuckGo invocations.

## Files Likely Affected

- `phase1-pablo/src/decisionlab/knowledge/retrieval/crag.py` —
  routing branch on `grading_failed`.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` —
  output marker.
- `phase1-pablo/src/decisionlab/runtime/usage.py` — counter.
- `phase1-pablo/tests/knowledge/retrieval/test_crag.py` — error-path
  test.

## Context

Phase spec: `docs/specs/memory-refactor/phase-2-retrieve-latency.md` (R4)
Heat: `crag-grader` (sequential after P2-001 — both touch
`crag.py` / `tool.py` routing).

## Completion Summary

**Commit:** `7346fbd` — `feat[knowledge]: distinguish CRAG grader errors from AMBIGUOUS (P2-004)`

### What was built
- Early-return branch in `evaluate_results`: when `_classify_results`
  emits the fail-closed sentinel, return immediately with
  `action="grader_unavailable"`, `web_results_used=0`, and the reranked
  results unchanged. Skips both `web_fallback` (all-INCORRECT) and the
  supplemented (has-AMBIGUOUS) branches.
- `_format_output` now accepts `grader_unavailable=True` and prepends a
  `[grader_unavailable]` marker to the header so the agent can read the
  verdict as provisional.
- `handle_retrieve_knowledge` increments the new `crag.grader_failed`
  telemetry counter when the evaluate path returns
  `grading_failed=True`. The counter is only bumped when CRAG actually
  ran — the rerank-skip path stays untouched.
- New test file `test_crag_grader_unavailable.py` covers AC1 (short
  circuit, no DuckDuckGo invocation), AC2 (output marker), and AC3
  (telemetry). Updated `test_crag.py::TestAC8_FailClosed` and
  `TestOOBHaikuIndex` to assert the new `grader_unavailable` action
  with zero web calls instead of the old `"supplemented"` routing.

### Files created/modified
- `phase1-pablo/src/decisionlab/knowledge/retrieval/crag.py` —
  `grading_failed` early return before web-fallback paths.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` —
  marker plumbing + `crag.grader_failed` counter wiring.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/models.py` —
  action enum comment updated to include `grader_unavailable` and
  `rerank_pass_through`.
- `phase1-pablo/tests/knowledge/retrieval/test_crag_grader_unavailable.py`
  — new test file, three AC-aligned classes.
- `phase1-pablo/tests/knowledge/test_crag.py` — `TestAC8_FailClosed`
  and `TestOOBHaikuIndex` re-aligned with the new routing.

### Decisions
- **Reuse the existing sentinel-string detection** (`grading_failed`
  was already plumbed through `CRAGResult` from P2-001's groundwork).
  No new flag, no schema change — the routing simply stops ignoring
  the bit it already had.
- **Counter named `crag.grader_failed`** to match the spec's R4
  bullet (the family is `crag.skipped` / `crag.evaluated` /
  `crag.grader_failed`).
- **Marker placed on the header** rather than per-result so the agent
  sees it immediately without parsing per-block metadata.
- **AC5 (slug-accuracy `p95_below: 2500`)** is integration-only and
  remains a manual probe — no automated test added because that
  requires live infrastructure.

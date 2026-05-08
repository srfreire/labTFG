---
id: P2-004
title: Distinguish CRAG grader errors from genuine AMBIGUOUS verdicts
status: todo
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

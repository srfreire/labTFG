---
id: P2-001
title: Skip CRAG when top rerank score is above confidence threshold
status: done
kind: strike
phase: 2
heat: crag-grader
priority: 1
blocked_by: [P1-004]
created: 2026-05-08
updated: 2026-05-08
---

# P2-001: Conditional CRAG

## Objective

Stop running CRAG (Haiku grader + optional web fallback) on every
retrieve. When the rerank already has a confident answer (top score
≥ threshold), pass through unchanged. Saves ~one Haiku round-trip
on the majority of queries — the largest single contributor to the
current 14–20s p95.

## Requirements

Per phase spec R1:

1. Add `crag_skip_threshold: float = 0.5` to
   `decisionlab.config.SETTINGS` (env override
   `DECISIONLAB_CRAG_SKIP_THRESHOLD`).
2. In
   `decisionlab/knowledge/retrieval/tool.py:handle_retrieve_knowledge`,
   after `fuse_and_rerank` returns, branch:
   - If `top_score >= SETTINGS.crag_skip_threshold`: short-circuit to
     `CRAGResult(results=reranked[:top_k * 2], action="rerank_pass_through",
     evaluations=[], web_results_used=0, grading_failed=False)`.
   - Else: call `evaluate_results(...)` as today.
3. Add a `record_usage`-style counter:
   `crag.skipped` and `crag.evaluated` per call (re-use
   `decisionlab.runtime.usage.record` patterns).
4. Tests cover: top score ≥0.5 → skip; top score <0.5 → evaluate;
   threshold tunable via env.

## Acceptance Criteria

- [x] AC1: `crag_skip_threshold` setting exists with default 0.5,
      env-overridable.
- [x] AC2: Skip branch returns `action="rerank_pass_through"` and
      makes zero LLM calls. Test asserts via mocked `evaluate_results`
      (call count = 0).
- [x] AC3: Evaluate branch behaves exactly as before for sub-threshold
      results. Existing CRAG tests still pass.
- [x] AC4: Telemetry records skip vs evaluate decisions per call.
- [ ] AC5: Smoke probe (20 queries against a populated KG) shows
      ≥50 % skip rate and a measurable p95 drop vs the pre-change
      baseline.
      *(deferred — eval-driven, requires real Voyage/ZeroEntropy/Neo4j
      infra; runs as a regression once the P2 chain lands. Same posture
      as the P1-004 AC5 smoke run.)*

## Files Likely Affected

- `phase1-pablo/src/decisionlab/config.py` — add
  `crag_skip_threshold`.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` —
  conditional branch.
- `phase1-pablo/src/decisionlab/runtime/usage.py` (or wherever
  counters live) — add `crag.skipped` / `crag.evaluated`.
- `phase1-pablo/tests/knowledge/retrieval/test_tool.py` — branch
  coverage.

## Context

Phase spec: `docs/specs/memory-refactor/phase-2-retrieve-latency.md` (R1)
Heat: `crag-grader`

## Completion Summary

**Commit:** `ce5393f` — `feat[knowledge]: skip CRAG when rerank top score is confident (P2-001)`

### What was built
- Added `SETTINGS.crag_skip_threshold` (default `0.5`, env override
  `DECISIONLAB_CRAG_SKIP_THRESHOLD`) via a new `_env_float` helper
  in `decisionlab.config`. Value is loaded once at module import
  alongside the other slot-named overrides.
- In `decisionlab.knowledge.retrieval.tool.handle_retrieve_knowledge`,
  computed `top_score = max((r.score for r in reranked[:top_k]), default=0.0)`
  immediately after the fuse/rerank stage. When the score is at or
  above the threshold, build a `CRAGResult(action="rerank_pass_through",
  results=reranked[:top_k * 2], evaluations=[], web_results_used=0,
  grading_failed=False)` directly and skip `evaluate_results` entirely.
  Sub-threshold path is unchanged.
- Hardened the no-rerank fallback (when no embedding service is
  available) by sorting the concatenated `kg + dense + sparse` results
  by score descending before slicing. The skip branch's `top_score`
  check assumes a sorted list; without this, an unranked early entry
  could spuriously trigger or block the skip in degraded mode.
- Wired `runtime.usage.increment_counter("crag.skipped")` and
  `increment_counter("crag.evaluated")` so the decision distribution
  surfaces in the same counters table P2-002 introduced. The actual
  counter helpers landed with P2-002; P2-001 just calls them.
- Covered AC1–AC4 in
  `tests/knowledge/retrieval/test_conditional_crag.py` (15 tests):
  default + env-override + bad-value of the setting; threshold
  boundary skip + above-threshold skip + sub-threshold evaluate; the
  `rerank_pass_through` action surfaces with `web_supplemented=False`
  through `_final_truncate`; threshold tunable so a high value forces
  evaluation on a confident rerank; counter snapshots reflect the
  branch taken; `increment_counter` accumulates and `reset()` clears
  both meters together. Module-level counter state is isolated
  per-test via an autouse fixture.
- Updated `tests/knowledge/test_retrieval_tool.py::test_stage_description_in_task_context`
  to use a sub-threshold score (`0.3`) so it still exercises the
  CRAG path it's testing (its fixture used `0.9` which now skips the
  grader).

### Files created/modified
- `phase1-pablo/src/decisionlab/config.py` — added `_env_float` helper
  and the `crag_skip_threshold: float` field on `Settings`. `_env_float`
  is also reused by P2-002's `ner_skip_threshold` after the rebase.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — added the
  skip branch, the `increment_counter` import, the `CRAGResult` import,
  and the score-descending sort on the no-rerank fallback. Tightened
  the conditional-CRAG comment.
- `phase1-pablo/tests/knowledge/retrieval/test_conditional_crag.py` —
  new file, AC1–AC4 coverage plus counter-helper smoke tests.
- `phase1-pablo/tests/knowledge/test_retrieval_tool.py` — sub-threshold
  score in the one task_context test that relied on CRAG always
  firing.

### Decisions
- **AC5 deferred** — same posture as P1-004 AC5: the smoke probe is
  eval-driven and requires a populated KG plus live Voyage / ZeroEntropy
  / Neo4j credentials. Unit tests fully exercise the skip-vs-evaluate
  contract; the latency win is a re-measurement against the P5
  `slug-accuracy.yaml` `p95_below: 2500` assertion once the full P2
  chain lands. Marking deferred rather than completed.
- **Reused `_env_float` from this PR for P2-002's `ner_skip_threshold`**
  during rebase. P2-002 had introduced its own `_env_float` (slot-prefixed)
  on main; the rebased state collapses to one helper with the slot
  convention to match `_env_model`.
- **Did not add a separate `reset_counters` API** — P2-002 chose to wipe
  both token-usage and named counters from a single `reset()` call.
  Aligned the P2-001 tests with that design rather than introducing a
  parallel "reset only counters" entry point.

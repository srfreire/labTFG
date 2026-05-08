---
id: P2-001
title: Skip CRAG when top rerank score is above confidence threshold
status: in-progress
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

- [ ] AC1: `crag_skip_threshold` setting exists with default 0.5,
      env-overridable.
- [ ] AC2: Skip branch returns `action="rerank_pass_through"` and
      makes zero LLM calls. Test asserts via mocked `evaluate_results`
      (call count = 0).
- [ ] AC3: Evaluate branch behaves exactly as before for sub-threshold
      results. Existing CRAG tests still pass.
- [ ] AC4: Telemetry records skip vs evaluate decisions per call.
- [ ] AC5: Smoke probe (20 queries against a populated KG) shows
      ≥50 % skip rate and a measurable p95 drop vs the pre-change
      baseline.

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

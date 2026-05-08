---
id: P2-002
title: Skip Haiku NER inside kg_retrieve when dense top-1 is decisive
status: todo
kind: strike
phase: 2
heat: ner
priority: 1
blocked_by: [P1-004]
created: 2026-05-08
updated: 2026-05-08
---

# P2-002: Skip NER on confident dense retrieval

## Objective

Avoid the Haiku NER call inside `kg_retrieve` when the dense
retrieval channel already has a strong answer. Today every retrieve
runs NER unconditionally; for a query like "list paradigms about
reward learning" where the dense top-1 is a direct paradigm hit, the
NER step is wasted latency.

## Requirements

Per phase spec R2:

1. Add `ner_skip_threshold: float = 0.7` to
   `decisionlab.config.SETTINGS` (env override
   `DECISIONLAB_NER_SKIP_THRESHOLD`).
2. In
   `decisionlab/knowledge/retrieval/tool.py:handle_retrieve_knowledge`,
   reorder so that `vector_retrieve` runs first. Capture the dense
   top-1 score.
3. If `dense_top1 >= SETTINGS.ner_skip_threshold`: skip
   `kg_retrieve` (pass `kg_results = []` into `fuse_and_rerank`).
   Otherwise call it as today.
4. Telemetry counter: `ner.skipped` / `ner.evaluated`.
5. Tests cover both branches.

## Acceptance Criteria

- [ ] AC1: `ner_skip_threshold` setting exists, default 0.7.
- [ ] AC2: When dense top-1 ≥ threshold, `kg_retrieve` is not called.
      Test asserts via mock.
- [ ] AC3: When dense top-1 < threshold or empty, `kg_retrieve` runs
      as today. Existing tests pass.
- [ ] AC4: Telemetry records skip vs evaluate.
- [ ] AC5: Smoke probe shows the NER skip rate and a p95 contribution
      reduction; combined with P2-001 the p95 budget assertion
      passes.

## Files Likely Affected

- `phase1-pablo/src/decisionlab/config.py` — add
  `ner_skip_threshold`.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` —
  reorder, conditional kg_retrieve call.
- `phase1-pablo/tests/knowledge/retrieval/test_tool.py` — branch
  coverage.

## Context

Phase spec: `docs/specs/memory-refactor/phase-2-retrieve-latency.md` (R2)
Heat: `ner` (independent of P2-001 / P2-003 / P2-004)

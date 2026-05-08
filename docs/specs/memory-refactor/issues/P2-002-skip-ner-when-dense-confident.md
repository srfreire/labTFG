---
id: P2-002
title: Skip Haiku NER inside kg_retrieve when dense top-1 is decisive
status: done
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

- [x] AC1: `ner_skip_threshold` setting exists, default 0.7.
- [x] AC2: When dense top-1 ≥ threshold, `kg_retrieve` is not called.
      Test asserts via mock.
- [x] AC3: When dense top-1 < threshold or empty, `kg_retrieve` runs
      as today. Existing tests pass.
- [x] AC4: Telemetry records skip vs evaluate.
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

## Completion Summary

**Commits:**
- `20383ee` — feat[knowledge]: skip Haiku NER when dense top-1 is decisive (P2-002)
- `57ae728` — feat[knowledge]: tighten P2-002 telemetry and test isolation
- `51563a7` — fix[knowledge]: ruff format config.py after ner_skip_threshold add

### What was built
- `SETTINGS.ner_skip_threshold` (default 0.7, env `DECISIONLAB_NER_SKIP_THRESHOLD`).
- `handle_retrieve_knowledge` now runs `vector_retrieve` first, captures
  `dense_top1`, and skips `kg_retrieve` (which carries the Haiku NER call)
  when the dense channel is already decisive.
- Skip path passes `kg_results = []` into `fuse_and_rerank`; RRF still merges
  sparse + dense as before.
- Counter mechanism (`runtime.usage.increment_counter` / `counters_snapshot`)
  modelled on the existing `record_usage` token meter, with three counters:
  `ner.skipped`, `ner.evaluated`, `ner.unavailable`.
- Test isolation: autouse fixture resets `_COUNTERS` between tests so per-test
  counter assertions are stable.
- Branch coverage: skip / evaluate / empty-dense / no-KG / runtime-tunable
  threshold (patches `SETTINGS` on the tool module).

### Files created/modified
- `phase1-pablo/src/decisionlab/config.py` — `ner_skip_threshold` field +
  `_env_float` helper.
- `phase1-pablo/src/decisionlab/runtime/usage.py` — `_Counters` thread-safe
  meter, `increment_counter`, `counters_snapshot`, `reset` extended.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — sequential
  vector → conditional kg flow with the threshold gate; dropped the now-dead
  `_noop_kg`/`_noop_vec` helpers and the `asyncio.gather` plumbing. Inline
  comment documents that the sequential ordering is deliberate.
- `phase1-pablo/tests/knowledge/test_retrieval_tool.py` — autouse counter
  reset fixture plus seven new tests under `TestEdgeCases`.

### Decisions
- Added `ner.unavailable` (not in spec) so `skipped + evaluated + unavailable`
  always sums to total retrieve calls — keeps skip-rate dashboards honest
  when the KG/embedding infra is missing.
- Sequential vector → kg ordering is by spec design; non-skip path now pays
  `T(vec) + T(kg)` instead of `max(T(vec), T(kg))`. The win is on the skip
  path, where the kg leg disappears entirely. An inline comment in `tool.py`
  warns against re-parallelising.
- AC5 left unchecked: it requires running `slug-accuracy.yaml` against a
  populated KG and is a phase-level measurement, not a unit test of this
  issue alone.

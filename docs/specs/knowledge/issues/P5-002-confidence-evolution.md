---
id: P5-002
title: Implement confidence evolution with corroboration, contradiction, and decay
status: done
kind: strike
phase: 5
heat: cross-run
priority: 2
blocked_by: [P5-001]
created: 2026-04-14
updated: 2026-04-15
---

# P5-002: Implement confidence evolution with corroboration, contradiction, and decay

## Objective
Make memory confidence scores dynamic — they increase when corroborated by independent runs, decrease when contradicted, decay with time, and strengthen with access frequency.

## Requirements
- **Corroboration boost** (already partially in P2-004 conflict resolution):
  - When a fact from run N matches an existing fact from run M (M != N) and is classified as CORROBORATION: `confidence += 0.05`, capped at 1.0
  - Also increment `corroborations` counter
  - The key addition here: ensure cross-run corroboration works (P2-004 handles single-run dedup, this ensures it works across runs)

- **Contradiction penalty**:
  - When classified as CONTRADICTION: old memory gets `confidence -= 0.10`, floored at 0.1
  - Increment `contradictions` counter on old memory
  - New memory starts with stage-default confidence (not reduced)
  - The contradiction is logged as an episodic memory: "Run {run_id} contradicted memory {memory_id}: {old_content} → {new_content}"

- **Access boost** (in `touch_memory`):
  - Each retrieval access: `confidence += 0.02`, capped at 1.0
  - This rewards memories that agents actually find useful

- **Time decay** (applied during consolidation):
  - For memories where `last_accessed_at` is >30 days ago:
    ```python
    periods = (now - last_accessed_at).days // 30
    confidence *= 0.95 ** periods
    ```
  - Only apply to memories with `memory_type != "reflection"` (reflections are higher-level and shouldn't decay as fast)
  - Floor confidence at 0.1 (never fully erase)

- **Confidence in retrieval scoring**:
  - The retrieval pipeline already has confidence as a Qdrant payload field
  - Add confidence as a multiplicative factor in final scoring: `final_score = reranked_score * recency_factor * confidence`
  - This means low-confidence memories are naturally deprioritized in retrieval

## Acceptance Criteria
- [x] AC1: A memory corroborated 3 times (from 3 independent runs) has confidence = initial + 3*0.05 (e.g., 0.6 → 0.75)
- [x] AC2: A contradicted memory has confidence decreased by 0.10 from its previous value
- [x] AC3: A memory accessed 10 times has confidence boosted by 10*0.02 = +0.20 (capped at 1.0)
- [x] AC4: Time decay reduces a 90-day-untouched memory's confidence by ~14% (0.95^3)
- [x] AC5: Retrieval results from high-confidence memories rank above equivalent low-confidence memories
- [x] AC6: Confidence never drops below 0.1 regardless of contradictions or decay

## Files Likely Affected
- `shared/shared/memories.py` — update `update_confidence`, `touch_memory` logic
- `phase1-pablo/src/decisionlab/knowledge/resolver.py` — cross-run corroboration/contradiction handling
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — confidence factor in final scoring

## Context
Phase spec: `docs/specs/knowledge/phase-5-cross-run-memory.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `cross-run`

## Completion Summary

**Commit:** `abc9ce0` — `feat[knowledge]: confidence evolution with corroboration, contradiction, and decay (P5-002)`

### What was built
- `update_confidence`: contradiction delta fixed to -0.10 (was -0.05), SQL-level clamping with `LEAST(1.0, GREATEST(0.1, ...))` for both corroboration and contradiction
- `touch_memory`: now boosts confidence by +0.02 per retrieval access, capped at 1.0
- `apply_time_decay(session)`: new consolidation function — decays memories not accessed in >30 days by `0.95^periods`, reflections exempt, confidence floored at 0.1
- Resolver CONTRADICTION branch: creates an episodic memory logging `"Run {run_id} contradicted memory {memory_id}: {old_content} → {new_content}"` in `meta` namespace
- `_apply_recency_weighting`: now multiplies by confidence factor (`final_score = reranked_score * recency_factor * confidence`), with defense-in-depth clamping of payload confidence to [0.0, 1.0]
- Timezone-safe handling in `apply_time_decay` (guards against both naive and tz-aware datetimes, NULL `last_accessed_at`)

### Files created/modified
- `shared/shared/memories.py` — modified `update_confidence`, `touch_memory`; added `apply_time_decay`, constants `_CONFIDENCE_CAP`, `_CONFIDENCE_FLOOR`, `_DECAY_RATE`, `_DECAY_PERIOD_DAYS`
- `phase1-pablo/src/decisionlab/knowledge/resolver.py` — added episodic memory creation in CONTRADICTION branch
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — added confidence factor to `_apply_recency_weighting`
- `phase1-pablo/tests/knowledge/test_confidence_evolution.py` — 17 tests covering all 6 ACs + edge cases (NULL timestamps, out-of-range confidence, tz-aware datetimes)

### Decisions
- Confidence clamping uses SQL-level `LEAST`/`GREATEST` for `update_confidence` and `touch_memory` (atomic, race-safe), but Python-level `max()` for `apply_time_decay` (operates on fetched rows in a loop)
- Episodic contradiction log uses `importance=3.0` and `confidence=1.0` — low importance since it's metadata, but full confidence since it's a factual event record
- `old_content` extraction moved before mutation calls for clarity (simplifier recommendation)
- Confidence factor in retrieval clamped to [0.0, 1.0] as defense-in-depth against bad payload data

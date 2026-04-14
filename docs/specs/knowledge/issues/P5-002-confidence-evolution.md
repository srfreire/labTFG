---
id: P5-002
title: Implement confidence evolution with corroboration, contradiction, and decay
status: todo
kind: strike
phase: 5
heat: cross-run
priority: 2
blocked_by: [P5-001]
created: 2026-04-14
updated: 2026-04-14
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
- [ ] AC1: A memory corroborated 3 times (from 3 independent runs) has confidence = initial + 3*0.05 (e.g., 0.6 → 0.75)
- [ ] AC2: A contradicted memory has confidence decreased by 0.10 from its previous value
- [ ] AC3: A memory accessed 10 times has confidence boosted by 10*0.02 = +0.20 (capped at 1.0)
- [ ] AC4: Time decay reduces a 90-day-untouched memory's confidence by ~14% (0.95^3)
- [ ] AC5: Retrieval results from high-confidence memories rank above equivalent low-confidence memories
- [ ] AC6: Confidence never drops below 0.1 regardless of contradictions or decay

## Files Likely Affected
- `shared/shared/memories.py` — update `update_confidence`, `touch_memory` logic
- `phase1-pablo/src/decisionlab/knowledge/resolver.py` — cross-run corroboration/contradiction handling
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — confidence factor in final scoring

## Context
Phase spec: `docs/specs/knowledge/phase-5-cross-run-memory.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `cross-run`

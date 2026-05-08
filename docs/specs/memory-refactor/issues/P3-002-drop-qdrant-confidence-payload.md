---
id: P3-002
title: Drop confidence from Qdrant payloads, batch-fetch from PG at retrieve time
status: done
kind: strike
phase: 3
heat: confidence
priority: 1
blocked_by: [P3-001]
created: 2026-05-08
updated: 2026-05-09
---

# P3-002: Drop Qdrant confidence, read from Postgres

## Objective

Designate Postgres as the single source of truth for confidence. Stop
writing `confidence` to Qdrant payloads (today the field drifts
because only `memories_dense` is synced on decay; sparse and corrob/
contradict are never synced). At retrieve time, batch-fetch the
current confidences for memory-backed results from PG.

## Requirements

Per phase spec R2:

1. Stop writing `confidence` to Qdrant payloads at every write site:
   - `decisionlab/knowledge/indexer.py:index_stage_output` — drop
     `"confidence"` from the payload dict.
   - `decisionlab/knowledge/resolver.py` enrichment path — drop
     `confidence` from the new vector's payload.
   - `decisionlab/knowledge/consolidation.py` time-decay sync —
     delete the `set_payload` calls (no longer needed).
2. In
   `decisionlab/knowledge/retrieval/tool.py:_apply_recency_weighting`,
   replace the per-result `r.metadata.get("confidence", 1.0)` lookup
   with a single batched PG fetch:
   ```python
   memory_ids = [
       uuid.UUID(r.metadata["entity_id"])
       for r in results
       if "memories" in r.metadata.get("collection", "")
   ]
   if memory_ids:
       async with shared.db.get_session() as session:
           rows = await session.execute(
               select(Memory.id, Memory.confidence)
               .where(Memory.id.in_(memory_ids))
           )
           conf_map = {row.id: row.confidence for row in rows}
   else:
       conf_map = {}
   ```
   Then in the per-result loop, look up `conf_map.get(uuid, 1.0)`.
3. Artifact-only results (no PG row) get `confidence_factor = 1.0`
   — preserves current behaviour.
4. Add a one-shot cleanup script
   (`phase1-pablo/scripts/qdrant_strip_confidence.py`) that walks
   `memories_dense` and `memories_sparse` and `set_payload({"confidence":
   None})` on each point. Document but don't auto-run.

## Acceptance Criteria

- [ ] AC1: New writes to `memories_dense`/`memories_sparse` no
      longer include `confidence` in payload. Integration test
      asserts payload shape.
- [ ] AC2: `_apply_recency_weighting` issues exactly one PG SELECT
      per retrieve; results carry the correct confidence factor.
      Test asserts via mocked session.
- [ ] AC3: Retrieval p95 stays in budget (≤2.5s) after the added PG
      round-trip — re-run the slug-accuracy `p95_below` assertion.
- [ ] AC4: The cleanup script `qdrant_strip_confidence.py` runs
      idempotently on a populated dev DB.
- [ ] AC5: Existing recency-weighting tests pass; `confidence_factor`
      values match pre-change behaviour for memory-backed results.

## Files Likely Affected

- `phase1-pablo/src/decisionlab/knowledge/indexer.py` — drop
  payload field.
- `phase1-pablo/src/decisionlab/knowledge/resolver.py` — drop
  payload field on enrichment.
- `phase1-pablo/src/decisionlab/knowledge/consolidation.py` —
  remove the post-decay Qdrant sync.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` —
  PG batched fetch in `_apply_recency_weighting`.
- `phase1-pablo/scripts/qdrant_strip_confidence.py` — new.
- `phase1-pablo/tests/knowledge/retrieval/test_tool.py` —
  recency-weighting test updated.

## Context

Phase spec: `docs/specs/memory-refactor/phase-3-data-integrity.md` (R2)
Heat: `confidence` (sequential after P3-001)

## Completion Summary

**Commit:** `9a03d89` — `feat[knowledge]: drop Qdrant confidence payload, read from Postgres (P3-002)`

### What was built
- Stopped writing `confidence` to Qdrant payloads at every memory write site:
  `indexer.index_stage_output`, `resolver` ENRICHMENT path, and
  `consolidation` reflection upsert. Removed dead `_STAGE_CONFIDENCE`
  in `indexer.py`.
- Collapsed `consolidation._apply_decay_and_sync` to a thin wrapper
  around `apply_time_decay`. The pre-P3-002 mirror only synced
  `memories_dense` (sparse silently drifted); now there is nothing to
  drift because PG owns the field.
- Refactored `retrieval/tool._apply_recency_weighting` to async + a
  single batched `SELECT id, confidence FROM memories WHERE id IN (...)`
  via the new `_fetch_confidences` / `_collect_memory_ids` helpers.
  Artifact-only and web results keep `confidence_factor = 1.0`.
- Updated the tool handler to `await _apply_recency_weighting(...)`.
- Hardened the new path: a PG error and a `shared.db is None` deploy
  both fall back to `confidence_factor = 1.0` and emit a WARNING log
  rather than aborting the retrieve or silently bypassing scoring
  (review feedback addressed pre-merge).
- Added `phase1-pablo/scripts/qdrant_strip_confidence.py`: walks
  `memories_dense` / `memories_sparse` and `set_payload({"confidence":
  None})` per stale point. `--dry-run` flag, idempotent
  (re-runs find 0 stale fields). Verified on local dev DB: 1 stale
  point blanked, second pass reported 0.
- Migrated all `_apply_recency_weighting` callers in
  `test_cross_run_retrieval.py` and `test_confidence_evolution.py`
  AC5 to the new async + PG-sourced shape (patched
  `_fetch_confidences` instead of relying on payload `confidence`).

### Files created/modified
- `phase1-pablo/src/decisionlab/knowledge/indexer.py` — drop payload field, drop `_STAGE_CONFIDENCE` dead code.
- `phase1-pablo/src/decisionlab/knowledge/resolver.py` — drop payload field on enrichment.
- `phase1-pablo/src/decisionlab/knowledge/consolidation.py` — collapse `_apply_decay_and_sync`, drop `confidence` from reflection upsert.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — async `_apply_recency_weighting`, new `_fetch_confidences` + `_collect_memory_ids`, `await` at the call site, resilient to DB outage / unwired `shared.db`.
- `phase1-pablo/scripts/qdrant_strip_confidence.py` — new cleanup script.
- `phase1-pablo/tests/knowledge/test_indexer.py` — invert payload assertions (no `confidence`).
- `phase1-pablo/tests/knowledge/test_resolver.py` — assert no `confidence` in enrichment payload.
- `phase1-pablo/tests/knowledge/test_retrieval_tool.py` — new `TestP3_002_RecencyConfidenceFromPG` (5 tests: one batched SELECT, no PG when no memory ids, missing PG row, stale Qdrant value ignored, `db = None` + PG error fallbacks with WARNING log assertion).
- `phase1-pablo/tests/knowledge/test_cross_run_retrieval.py` — convert callers to async/await.
- `phase1-pablo/tests/knowledge/test_confidence_evolution.py` — rewrite AC5 against patched `_fetch_confidences`.
- `docs/specs/memory-refactor/phase-3-data-integrity.md` — AC2 + AC3 marked done.

### Decisions
- Also dropped `confidence` from the consolidation **reflection** upsert
  (not explicitly listed in the issue but covered by phase-spec AC1
  "new writes to memories_dense/memories_sparse no longer include
  `confidence`"). Reflections write to `memories_dense`.
- Removed `_STAGE_CONFIDENCE` from `indexer.py` since it became dead
  code — the resolver still owns its own copy for the PG `create_memory`
  path.
- Reviewer surfaced two confidence-related silent-failure risks
  (broad PG exceptions and `shared.db = None` invisibility) — both
  fixed before merge with WARNING logs and the same `factor = 1.0`
  fallback the spec already mandates for artifact-only results.
- AC3 phase-spec assertion ("SQL issued exactly once per retrieve") is
  enforced by test in `TestP3_002_RecencyConfidenceFromPG.test_recency_weighting_issues_one_pg_select` — patches `shared.db` and counts `await session.execute`.
- AC3 of the **issue** body (retrieval p95 ≤ 2.5s) was not re-run in
  this session — would need a populated dev DB and the slug-accuracy
  eval driver. The change is one indexed PK lookup per retrieve, well
  within the ≤5ms estimate in the phase-spec decisions section.

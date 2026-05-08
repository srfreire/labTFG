---
id: P3-002
title: Drop confidence from Qdrant payloads, batch-fetch from PG at retrieve time
status: todo
kind: strike
phase: 3
heat: confidence
priority: 1
blocked_by: [P3-001]
created: 2026-05-08
updated: 2026-05-08
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

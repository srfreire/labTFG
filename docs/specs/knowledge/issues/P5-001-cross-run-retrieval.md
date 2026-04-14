---
id: P5-001
title: Enable cross-run retrieval with recency weighting
status: todo
kind: strike
phase: 5
heat: cross-run
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-14
---

# P5-001: Enable cross-run retrieval with recency weighting

## Objective
Configure the retrieval pipeline to search across all pipeline runs (not just the current one), apply recency-based score boosting so recent knowledge ranks higher, and exclude current-run results to avoid self-retrieval.

## Requirements
- **Default cross-run scope**: retrieval queries search Qdrant and Neo4j across all runs. The `exclude_run_id` filter prevents retrieving chunks from the current run.
- This should already be partially implemented in P3-002 (dense/sparse retrieval with `exclude_run_id` filter) — this issue ensures it works end-to-end across runs and adds recency weighting.

- **Recency weighting:**
  - After reranking (P3-003), apply recency boost as a score multiplier:
    ```python
    days_old = (now - memory.created_at).days
    recency_factor = 0.995 ** days_old
    final_score = reranked_score * recency_factor
    ```
  - Re-sort results by `final_score` after applying recency
  - Add `recency_factor` to result metadata for transparency
  - Apply in the `retrieve_knowledge` tool handler (P3-005) after the fusion+rerank pipeline

- **Run metadata in results**: each `RetrievalResult` metadata includes `run_id` and `run_date` so agents can see provenance (e.g., "this fact comes from a run 3 days ago on food intake")

- **Cross-run KG queries**: the KG retrieval (P3-001) already traverses all nodes regardless of run. Add run_id metadata to returned passages so agents know the source run.

## Acceptance Criteria
- [ ] AC1: A retrieval query in run 3 returns results from runs 1 and 2 but not run 3
- [ ] AC2: A fact from run 2 (yesterday) scores higher than the same fact from run 1 (30 days ago) due to recency weighting
- [ ] AC3: Recency factor for a 0-day-old memory is 1.0; for a 30-day-old memory is ~0.86; for a 365-day-old memory is ~0.16
- [ ] AC4: Result metadata includes `run_id` and `run_date` for all results
- [ ] AC5: KG traversal results include run_id provenance on relation properties

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — add recency weighting in handler
- `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py` — include run_id in passage metadata
- `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py` — include run_id in result metadata

## Context
Phase spec: `docs/specs/knowledge/phase-5-cross-run-memory.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `cross-run`

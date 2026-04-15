---
id: P5-001
title: Enable cross-run retrieval with recency weighting
status: done
kind: strike
phase: 5
heat: cross-run
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-15
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
- [x] AC1: A retrieval query in run 3 returns results from runs 1 and 2 but not run 3
- [x] AC2: A fact from run 2 (yesterday) scores higher than the same fact from run 1 (30 days ago) due to recency weighting
- [x] AC3: Recency factor for a 0-day-old memory is 1.0; for a 30-day-old memory is ~0.86; for a 365-day-old memory is ~0.16
- [x] AC4: Result metadata includes `run_id` and `run_date` for all results
- [x] AC5: KG traversal results include run_id provenance on relation properties

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — add recency weighting in handler
- `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py` — include run_id in passage metadata
- `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py` — include run_id in result metadata

## Context
Phase spec: `docs/specs/knowledge/phase-5-cross-run-memory.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `cross-run`

## Completion Summary

**Commit:** `c7ffb04` — `feat[knowledge]: cross-run retrieval with recency weighting (P5-001)`

### What was built
- Recency weighting function (`_apply_recency_weighting`) using Generative Agents decay pattern: `score *= 0.995^days_old`
- Applied after CRAG evaluation, before formatting — results re-sorted by weighted score
- `run_id`, `run_date`, `run_ids` metadata added to KG retrieval results from node properties
- `rel_run_ids` added to KG passages from relation-level provenance (AC5)
- `run_date` alias for `created_at` added to vector retrieval results
- Fixed pre-existing frozen dataclass mutation bug in `sparse_retrieve` score normalization

### Files created/modified
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — added `_apply_recency_weighting`, `_RECENCY_DECAY`, integrated after CRAG
- `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py` — added `rel_run_ids` to `_ScoredNode`, modified PPR Cypher to return relation `run_id`s, enriched `_collect_passages` metadata
- `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py` — added `run_date` to `_to_results`, fixed frozen dataclass mutation in sparse normalization
- `phase1-pablo/tests/knowledge/test_cross_run_retrieval.py` — 19 tests covering all 5 ACs + edge cases

### Decisions
- Recency weighting applied after CRAG (not before) so semantic quality evaluation is unaffected by age
- Results without timestamps get `recency_factor=1.0` (no penalty) — safe for web fallback results
- `run_ids[-1]` used as primary `run_id` for KG nodes, relying on `populate_kg`'s chronological append contract

---
id: P5-002
title: Remove IdRegistry, simplify PipelineState to slugs
status: in-progress
kind: strike
phase: 5
heat: pipeline
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-14
started: 2026-04-14
---

# P5-002: Remove IdRegistry, simplify PipelineState to slugs

## Objective
Delete the IdRegistry class and all T-P-F ID generation. PipelineState uses plain slugs for paradigms and formulations throughout.

## Requirements

### Delete IdRegistry
- Delete `src/decisionlab/id_registry.py`
- Remove `ids: IdRegistry` field from `PipelineState`
- Remove `topic_id` property, `assign_paradigm_id`, `assign_formulation_id`, `get_id`, `get_slug` delegation methods

### PipelineState field changes
- `selected_formulations`: changes from `{slug: [T-P-F ids]}` to `{slug: [formulation_slug]}`
- `approved_specs`: changes from `list[str]` of T-P-F IDs to `dict[str, list[str]]` = `{paradigm_slug: [formulation_slug]}`
- Remove all IdRegistry-related serialization from `save()`/`load()`

### Router stage updates
- `_review_research`: remove `state.assign_paradigm_id(slug)` calls — just store approved slugs
- `_review_formalize`: call `_convert_formulations_to_slugs` instead of `_convert_formulations_to_ids`
- `_convert_formulations_to_ids` → `_convert_formulations_to_slugs`: parse formulation headers, return `{slug: [slugified_name]}` using existing `slugify()` from `tools/reports.py`

### Tree map rewrite
- `generate_tree_map` in `tools/reports.py`: use paradigm names from deep reports and formulation names from `selected_formulations`, no IDs
- Remove `IdRegistry` import from reports.py

### Feedback/mock updates
- Remove any remaining IdRegistry references from `feedback.py`, `web_feedback.py`, `mock_server.py`

### Tests
- Rewrite `tests/test_pipeline_state.py`: remove all IdRegistry tests, update for slug-based API
- Update `tests/test_feedback_helpers.py` if needed

## Acceptance Criteria
- [x] `id_registry.py` does not exist
- [x] No imports of `IdRegistry` anywhere in codebase
- [x] `PipelineState` has no `ids` field, no `topic_id`
- [x] `selected_formulations` values are formulation slugs (not T-P-F IDs)
- [x] `approved_specs` is `dict[str, list[str]]` keyed by paradigm slug
- [x] Tree map renders with human-readable names (no T01-P01 prefixes)
- [x] `_convert_formulations_to_slugs` uses `slugify()` to derive formulation slugs
- [x] All tests in `test_pipeline_state.py` and `test_feedback_helpers.py` pass

## Files Likely Affected
- `src/decisionlab/id_registry.py` — DELETE
- `src/decisionlab/router.py` — PipelineState, _convert, _review_research, _review_formalize
- `src/decisionlab/tools/reports.py` — generate_tree_map rewrite
- `src/decisionlab/feedback.py` — remove IdRegistry refs if any
- `src/decisionlab/web_feedback.py` — same
- `src/decisionlab/mock_server.py` — same
- `tests/test_pipeline_state.py` — full rewrite
- `tests/test_feedback_helpers.py` — update as needed

## Context
Phase spec: `docs/specs/infrastructure/phase-5-slug-wiring.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `pipeline`

## Completion Summary

**Commit:** `a44ca17` — `feat[pipeline]: remove IdRegistry, simplify PipelineState to slugs (P5-002)`

### What was built
- Deleted `IdRegistry` class and all T-P-F ID generation (T01-P01-F01 scheme)
- Replaced with slug-based naming using existing `slugify()` from `tools/reports.py`
- `approved_specs` changed from flat `list[str]` to `dict[str, list[str]]` keyed by paradigm slug
- Re-run cascade simplified from T-P-F prefix matching to direct dict key lookup
- Tree map now renders human-readable names without ID prefixes

### Files created/modified
- `src/decisionlab/id_registry.py` — DELETED
- `src/decisionlab/router.py` — removed IdRegistry, added `_convert_formulations_to_slugs`, updated all stage handlers
- `src/decisionlab/tools/reports.py` — rewrote `generate_tree_map` to use `selected_formulations` directly
- `tests/test_pipeline_state.py` — full rewrite for slug-based API (30 → 8 tests, IdRegistry tests removed)
- `tests/test_feedback_helpers.py` — T-P-F IDs → formulation slugs in fixtures
- `tests/test_router_review_build.py` — slugs + dict-based `approved_specs`
- `tests/test_router_review_reason.py` — slugs + dict-based `approved_specs`
- `tests/test_web_feedback.py` — T-P-F IDs → formulation slugs in fixtures
- `tests/tools/test_reports.py` — rewrote tree map tests with async/mock storage

### Decisions
- `approved_specs` grouping derived from `selected_formulations` in the router rather than changing feedback function signatures
- Feedback functions (`feedback.py`, `web_feedback.py`) unchanged — they are string-agnostic and naturally pass through slug values
- `mock_server.py` unchanged — no IdRegistry references to remove

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
- [ ] `id_registry.py` does not exist
- [ ] No imports of `IdRegistry` anywhere in codebase
- [ ] `PipelineState` has no `ids` field, no `topic_id`
- [ ] `selected_formulations` values are formulation slugs (not T-P-F IDs)
- [ ] `approved_specs` is `dict[str, list[str]]` keyed by paradigm slug
- [ ] Tree map renders with human-readable names (no T01-P01 prefixes)
- [ ] `_convert_formulations_to_slugs` uses `slugify()` to derive formulation slugs
- [ ] All tests in `test_pipeline_state.py` and `test_feedback_helpers.py` pass

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

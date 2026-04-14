---
id: P5-004
title: Register models at approval + finalize run record
status: done
kind: strike
phase: 5
heat: registration
priority: 2
blocked_by: [P5-001, P5-003]
created: 2026-04-14
updated: 2026-04-15
---

# P5-004: Register models at approval + finalize run record

## Objective
Insert `Model` rows into Postgres when the user approves builds in REVIEW_BUILD. Populate `runs.s3_report_key` when the pipeline completes.

## Requirements

### Model registration in _review_build
- After user approves a build, for each approved `(paradigm_slug, formulation_slug)`:
  - Read the Python model file from S3: `models/{run_id}/builder/{paradigm}/{formulation}_model.py`
  - Extract `class_name` via regex (`class (\w+)` pattern)
  - INSERT `Model` row: `id=uuid4()`, `run_id`, `paradigm`, `formulation`, `class_name`, `s3_model_key`, `s3_test_key`
  - `s3_model_key` = `models/{run_id}/builder/{paradigm}/{formulation}_model.py`
  - `s3_test_key` = `models/{run_id}/builder/{paradigm}/test_{formulation}.py`
- Only register approved models (not rejected/re-run ones)
- Handle re-runs: if model already registered (same run_id + paradigm + formulation), UPDATE instead of INSERT

### Run finalization
- At pipeline completion (status → "done"), SET `runs.s3_report_key = "research/{run_id}/report.md"`
- Both in `server.py` (web path) and `cli.py` (CLI path)

### Edge cases
- Builder re-run: old Model row should be updated with new S3 keys
- Model file doesn't exist in S3 (agent failed silently): skip registration, log warning

## Acceptance Criteria
- [x] Approved models have `Model` rows in Postgres after REVIEW_BUILD
- [x] `Model.paradigm` and `Model.formulation` are slug values
- [x] `Model.s3_model_key` and `Model.s3_test_key` point to correct S3 paths
- [x] `Model.class_name` extracted correctly from Python source
- [x] `runs.s3_report_key` populated when pipeline finishes
- [x] Re-run of a previously approved model updates the existing row
- [x] Missing model file in S3 logs warning, does not crash

## Files Likely Affected
- `src/decisionlab/router.py` — _review_build: model registration logic
- `src/decisionlab/server.py` — run finalization (s3_report_key)
- `src/decisionlab/cli.py` — run finalization (s3_report_key)

## Context
Phase spec: `docs/specs/infrastructure/phase-5-slug-wiring.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `registration`

## Completion Summary

**Commit:** `01dd71a` — `feat[router]: register models at approval + finalize run record (P5-004)`

### What was built
- `_register_approved_models()` method on Router: iterates `approved_specs`, reads model source from S3, extracts `class_name` via regex, upserts Model row in Postgres
- Re-run handling: SELECT by `(run_id, paradigm, formulation)` unique constraint — UPDATE if exists, INSERT otherwise
- Missing model file: logs warning and skips without crash
- Run finalization: `s3_report_key` set to `research/{run_id}/report.md` at pipeline completion in Router.run(), server.py, and cli.py

### Files created/modified
- `phase1-pablo/src/decisionlab/router.py` — added `_register_approved_models()`, called in `_review_build` before DONE; added `s3_report_key` finalization in `run()`
- `phase1-pablo/src/decisionlab/server.py` — added `s3_report_key` to the post-pipeline Run status update
- `phase1-pablo/src/decisionlab/cli.py` — added `s3_report_key` finalization in both `run` and `resume` commands
- `phase1-pablo/tests/test_router_review_build.py` — 5 new tests (model registration, class extraction, missing file, re-run update, S3 path correctness); existing 4 tests updated to mock DB

### Decisions
- Model registration placed in `_review_build` (not `_do_build`) per spec: only approved models are registered
- `s3_report_key` finalization added to Router.run() post-loop AND explicitly in server.py/cli.py for defense-in-depth

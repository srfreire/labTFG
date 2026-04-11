---
id: P2-001
title: Add run_id concept and shared.init to Phase 1 pipeline
status: done
kind: strike
phase: 2
heat: pipeline
priority: 1
blocked_by: [P1-006]
created: 2026-04-11
updated: 2026-04-11
---

# P2-001: Add run_id concept and shared.init to Phase 1 pipeline

## Objective
Introduce a UUID `run_id` per pipeline execution, create a Run record in Postgres, and bootstrap shared infrastructure in Phase 1 entry points.

## Requirements
- Add `run_id: str` field to `PipelineState` in `router.py`
- On pipeline start: `await shared.init()`, create `Run` record in Postgres, assign UUID to `run_id`
- Replace `reports_dir: Path` parameter with `run_id: str` throughout the pipeline chain:
  - `Router.__init__`, `Researcher.__init__`, `DeepResearcher.__init__`, `Formalizer.__init__`, `Reasoner.__init__`, `Builder.__init__`
  - All sub-agents that receive `reports_dir`
- S3 key prefix pattern: `research/{run_id}/` for reports, `models/{run_id}/` for builder output
- Add helper method to `PipelineState` or utility: `research_prefix(run_id)` and `models_prefix(run_id)`
- Update CLI entry points (`cli.py`): call `shared.init()` at startup, `shared.shutdown()` at exit, replace `_reports_dir()` with run_id creation
- Update server entry point (`server.py`): same pattern
- `decisionlab resume` command: accept `--run-id` instead of `--reports-dir`
- Add `shared` dependency already exists in Phase 1's pyproject.toml — verify it points to the updated shared package

## Acceptance Criteria
- [x] `decisionlab run "problem"` creates a Run record in Postgres with a UUID
- [x] `run_id` is threaded through all agents (Researcher, Formalizer, Reasoner, Builder)
- [x] `reports_dir: Path` parameter no longer exists in any agent constructor
- [x] `shared.init()` called on startup, `shared.shutdown()` called on exit
- [x] `decisionlab resume --run-id <uuid>` works (loads Run from Postgres)

## Files Likely Affected
- `phase1-pablo/src/decisionlab/router.py` — PipelineState, reports_dir → run_id
- `phase1-pablo/src/decisionlab/cli.py` — entry points, shared.init/shutdown
- `phase1-pablo/src/decisionlab/server.py` — entry point, shared.init/shutdown
- `phase1-pablo/src/decisionlab/agents/researcher.py` — constructor param
- `phase1-pablo/src/decisionlab/agents/deep_researcher.py` — constructor param
- `phase1-pablo/src/decisionlab/agents/formalizer.py` — constructor param
- `phase1-pablo/src/decisionlab/agents/reasoner.py` — constructor param
- `phase1-pablo/src/decisionlab/agents/builder.py` — constructor param
- `phase1-pablo/pyproject.toml` — verify shared dependency

## Context
Phase spec: `docs/specs/infrastructure/phase-2-phase1-integration.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `pipeline`

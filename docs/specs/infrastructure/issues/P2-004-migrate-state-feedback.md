---
id: P2-004
title: Migrate Phase 1 pipeline state and feedback to StorageService
status: in-progress
kind: strike
phase: 2
heat: pipeline
priority: 2
blocked_by: [P2-001]
created: 2026-04-11
updated: 2026-04-11
---

# P2-004: Migrate Phase 1 pipeline state and feedback to StorageService

## Objective
Move pipeline state persistence, feedback formulation filtering, env_spec uploads, and validation file cleanup to S3.

## Requirements
- `PipelineState.save()` in `router.py`:
  - Serialize state to JSON
  - `await storage.put_text(f"research/{run_id}/pipeline_state.json", json_str)`
  - Remove atomic temp file write logic (no longer needed with S3 PUT)
- `PipelineState` resume/load:
  - `await storage.get_text(f"research/{run_id}/pipeline_state.json")`
  - Deserialize and reconstruct state
- `feedback.review_formalize()`:
  - Read formulation: `await storage.get_text(f"research/{run_id}/formulations/{slug}.md")`
  - Filter selected formulations
  - Write filtered version back: `await storage.put_text(...)`
- `web_feedback.review_formalize()`:
  - Same pattern as CLI feedback
- `env_spec` upload:
  - CLI `reason` command: upload env_spec file to `research/{run_id}/env_spec.json` via `storage.put()`
  - `web_feedback.get_env_spec()`: upload parsed JSON to S3 instead of temp file + shutil.copy2
  - `Router._get_env_spec()`: read from S3 instead of local path
- Validation file deletion in `Router._review_build()`:
  - `await storage.delete(f"models/{run_id}/builder/{fid}_validation.json")`
- Update `Run` status in Postgres as pipeline progresses

## Acceptance Criteria
- [ ] Pipeline state saves to MinIO at `research/{run_id}/pipeline_state.json`
- [ ] `decisionlab resume --run-id <uuid>` loads state from S3 and continues
- [ ] Feedback formulation filtering reads from and writes to S3
- [ ] Env spec uploaded to S3 at `research/{run_id}/env_spec.json`
- [ ] Stale validation files deleted from S3
- [ ] Run status updated in Postgres at each stage
- [ ] No local filesystem writes (no temp files, no shutil.copy2)

## Files Likely Affected
- `phase1-pablo/src/decisionlab/router.py` — PipelineState.save(), _review_build(), _get_env_spec()
- `phase1-pablo/src/decisionlab/feedback.py` — review_formalize()
- `phase1-pablo/src/decisionlab/web_feedback.py` — review_formalize(), get_env_spec()
- `phase1-pablo/src/decisionlab/cli.py` — reason command env_spec handling

## Context
Phase spec: `docs/specs/infrastructure/phase-2-phase1-integration.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `pipeline`

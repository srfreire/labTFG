---
id: P3-003
title: Migrate orchestrator experiment lifecycle and analyst tools to async Postgres + S3
status: in-progress
kind: strike
phase: 3
heat: core
priority: 3
blocked_by: [P3-002]
created: 2026-04-11
updated: 2026-04-11
---

# P3-003: Migrate orchestrator experiment lifecycle and analyst tools to async Postgres + S3

## Objective
Replace all SQLite store calls with async Postgres and move large JSON blobs to S3.

## Requirements

### Orchestrator experiment lifecycle (`orchestrator.py`)
- Remove `from shared.store import ...` — use `shared.db.get_session()` instead
- `create_environment` tool:
  - `async with shared.db.get_session() as s: s.add(Experiment(id=uuid, description=...))` 
  - `update`: set `spec` JSONB column
- `run_simulation` tool:
  - Upload events JSON: `await storage.put_text(f"experiments/{exp_id}/events.json", ...)`
  - Upload replay JSON: `await storage.put_text(f"experiments/{exp_id}/replay.json", ...)`
  - Update experiment row: `s3_events_key`, `s3_replay_key`, `models_used`, `steps`, `seed`, `status=SIMULATED`
- `observe_simulation` tool:
  - Upload tracker JSON: `await storage.put_text(f"experiments/{exp_id}/tracker.json", ...)`
  - Update: `s3_tracker_key`, `status=TRACKED`
- `analyze_results` tool:
  - Upload analyst JSON: `await storage.put_text(f"experiments/{exp_id}/analyst.json", ...)`
  - Update: `s3_analyst_key`, `status=ANALYZED`
- `generate_report` tool:
  - Query artifacts table or S3 for PDFs instead of `output_dir.glob("*.pdf")`
  - Update: `s3_pdf_key`, `status=REPORTED`
- `list_experiments` tool: async Postgres SELECT
- `read_predictions` tool:
  - Needs `run_id` context — determine from selected model's `run_id` FK
  - `await storage.get_text(f"research/{run_id}/deep/{slug}.md")`

### Analyst tools (`tools.py`)
- `list_past_experiments` → async Postgres query via `shared.db.get_session()`
- `get_experiment_analysis` → async Postgres query, download `tracker_json` and `analyst_json` from S3 if needed

### Remove old store dependency
- Remove `shared.store` imports from orchestrator.py and tools.py
- Remove `init_db()` call from `Orchestrator.__init__`

## Acceptance Criteria
- [ ] `create_experiment` creates row in async Postgres
- [ ] Events, replay, tracker, analyst JSON stored in S3 with keys in DB
- [ ] Experiment status progresses correctly through lifecycle
- [ ] `list_experiments` returns from Postgres
- [ ] `read_predictions` reads from S3 using model's run_id
- [ ] PDF discovery uses DB/S3 instead of filesystem glob
- [ ] Analyst `list_past_experiments` and `get_experiment_analysis` use async Postgres
- [ ] No `shared.store` imports remain in orchestrator.py or tools.py
- [ ] Full pipeline works: create env → simulate → track → analyze → report

## Files Likely Affected
- `phase2-juan/simlab/orchestrator.py` — all store.* calls, read_predictions, generate_report PDF handling
- `phase2-juan/simlab/tools.py` — analyst tool functions

## Context
Phase spec: `docs/specs/infrastructure/phase-3-phase2-integration.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `core`

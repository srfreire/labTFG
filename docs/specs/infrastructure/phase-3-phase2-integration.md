# Phase 3: Phase 2 Integration

> Status: current | Created: 2026-04-11 | Last updated: 2026-04-11
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Migrate all Phase 2 file reads from local filesystem to StorageService (MinIO) and replace SQLite store with async Postgres. Phase 2 reads Phase 1 artifacts (models, research) and writes its own outputs (PDFs, charts, experiment data).

## Requirements

### R1: Bootstrap shared infrastructure in api.py

- Remove `RESEARCH_DIR`, `OUTPUT_DIR`, `BUILDER_DIR` path variables and `_env_path()` helper
- Call `await shared.init()` on app startup (FastAPI lifespan)
- Call `await shared.shutdown()` on app shutdown
- Pass `shared.storage` and `shared.db` to Orchestrator constructor
- Orchestrator constructor no longer takes `research_dir`, `output_dir`, `builder_dir` Path params

### R2: Migrate model loader to S3 + Postgres

- `discover_models()` → query Postgres `models` table instead of globbing `BUILDER_DIR`
- `load_model()` → download `*_model.py` from S3 to a temp dir, `importlib.util.spec_from_file_location` from temp path, clean up after experiment ends
- `register_model()` → already done by Phase 1 pipeline; Phase 2 just reads
- Remove `shared.store.init_db()` and `shared.store.register_model()` calls from model_loader
- Update Orchestrator call sites for `discover_models` and `load_model` (signature changes)

### R3: Migrate orchestrator experiment lifecycle to async Postgres + S3

- Replace all `shared.store.*` calls with async Postgres via `shared.db.get_session()`:
  - `create_experiment` → `INSERT INTO experiments`
  - `update_experiment` → `UPDATE experiments`
  - `list_experiments` → `SELECT FROM experiments`
- Large JSON blobs → write to S3 instead of storing in DB:
  - `events_json` → `storage.put_text(f"experiments/{exp_id}/events.json", ...)`; store key in `s3_events_key`
  - `replay_json` → `storage.put_text(f"experiments/{exp_id}/replay.json", ...)`; store key in `s3_replay_key`
  - `tracker_json` → `storage.put_text(f"experiments/{exp_id}/tracker.json", ...)`; store key in `s3_tracker_key`
  - `analyst_json` → `storage.put_text(f"experiments/{exp_id}/analyst.json", ...)`; store key in `s3_analyst_key`
- `read_predictions` → `storage.get_text(f"research/{run_id}/deep/{slug}.md")`
  - Orchestrator needs to know which `run_id` to read from — present available runs to user
- PDF discovery → query `artifacts` table or list S3 prefix instead of globbing `OUTPUT_DIR`
- Analyst tools in `tools.py` → async Postgres queries

### R4: Migrate reporter and charts output to S3

- `read_research` tool → `storage.get_text(f"research/{run_id}/{path}")` with prefix guard
- `compile_report`:
  - LaTeX template stays on local filesystem (bundled with package, not an artifact)
  - Write assembled `.tex` to temp dir
  - Run `tectonic` on temp dir
  - Upload `.tex` and `.pdf` to S3 at `experiments/{exp_id}/report.tex` and `.pdf`
  - Register artifacts
- Chart PNGs in `charts.py`:
  - Render matplotlib to temp file
  - Upload PNG to S3 at `experiments/{exp_id}/charts/chart_{n}.png`
  - Chart spec `image_path` → S3 key instead of local path
  - For LaTeX `\includegraphics`: download PNGs to temp dir before tectonic compile

## Acceptance Criteria

- [ ] AC1: `shared.init()` called on FastAPI startup, `shared.shutdown()` on shutdown
- [ ] AC2: Orchestrator no longer accepts filesystem path parameters
- [ ] AC3: `discover_models()` returns models from Postgres (not filesystem glob)
- [ ] AC4: `load_model()` downloads model from S3, loads via importlib, model runs correctly
- [ ] AC5: `create_experiment` / `update_experiment` use async Postgres
- [ ] AC6: Large JSON blobs (events, replay, tracker, analyst) stored in S3, keys in DB
- [ ] AC7: `read_predictions` reads from S3
- [ ] AC8: Analyst cross-experiment tools query async Postgres
- [ ] AC9: Reporter reads research files from S3
- [ ] AC10: Reporter writes .tex and .pdf to S3
- [ ] AC11: Charts write PNGs to S3
- [ ] AC12: Full pipeline works end-to-end: greeting → simulation → tracker → analyst → reporter

## Technical Notes

- Phase 2 file I/O surfaces:
  - `api.py` — path config (lines 43-51), Orchestrator construction (line 105-110)
  - `model_loader.py` — `discover_models()` glob (line 58), `load_model()` importlib (line 116), `register_model` (line 85)
  - `orchestrator.py` — `read_predictions` (line 460), PDF glob (line 651), all `store.*` calls (lines 356-669)
  - `reporter.py` — `read_research` (line 112), `compile_report` .tex write (line 132), template read (line 125)
  - `charts.py` — `fig.savefig` PNG write (line 282)
  - `tools.py` — analyst `list_experiments` / `get_experiment` (lines 264, 272)
- The `Orchestrator` needs to track which `run_id` the user is working with for S3 key construction
- LaTeX template (`simlab/templates/report_template.tex`) stays local — it's package code, not an artifact
- `tectonic` subprocess needs local `.tex` and chart PNGs — download to temp dir, compile, upload results

## Decisions

| Decision | Rationale |
|----------|-----------|
| LaTeX template stays local | It's bundled code, not a user artifact; changes with package version |
| tectonic via temp dir | Subprocess needs local files; same pattern as Builder pytest |
| Orchestrator presents available runs | User needs to pick which Phase 1 run's models to use |
| Analyst tools go async | They're in orchestrator's async pipeline already |

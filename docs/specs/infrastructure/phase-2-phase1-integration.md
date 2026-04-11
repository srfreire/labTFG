# Phase 2: Phase 1 Integration

> Status: current | Created: 2026-04-11 | Last updated: 2026-04-11
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Migrate all Phase 1 file I/O from local filesystem to StorageService (MinIO) and register pipeline runs in Postgres. Introduces the `run_id` concept — each pipeline execution gets a UUID, and all artifacts are stored under S3 prefixes keyed by that ID.

## Requirements

### R1: Run ID concept and shared infrastructure init

- `PipelineState` gains a `run_id: str` field (UUID)
- On pipeline start (CLI `run` or server `run_pipeline`), create a `Run` record in Postgres via `shared.db`
- Call `await shared.init()` at startup in both CLI and server entry points
- Call `await shared.shutdown()` at exit
- Replace `reports_dir: Path` parameter threading with `run_id: str` throughout the pipeline
- All S3 key construction follows the pattern: `research/{run_id}/...` and `models/{run_id}/...`

### R2: Migrate report tools to StorageService

- `save_deep_report` → `storage.put_text(f"research/{run_id}/deep/{slug}.md", content)`
- `save_summary_report` → `storage.put_text(f"research/{run_id}/report.md", summary)`
- `generate_tree_map` → `storage.get_text(...)` to read report, modify, `storage.put_text(...)` to write back
- `create_read_report` → `storage.get_text(...)` to read deep reports
- Register each report artifact in `artifacts` table

### R3: Migrate file tools to StorageService

- `create_write_file(base_prefix)` → writes to S3 under the given prefix
- `create_read_file(base_prefix)` → reads from S3 under the given prefix
- Builder pytest handling: after Builder writes `*_model.py` and `test_*.py` to S3, download both to a temp directory, run pytest there, clean up temp dir after
- Register each artifact (formulations, reasoner specs, models, tests) in `artifacts` table

### R4: Migrate pipeline state and feedback to StorageService

- `PipelineState.save()` → serialize to JSON, `storage.put_text(f"research/{run_id}/pipeline_state.json", ...)`
- `PipelineState.load()` (resume) → `storage.get_text(...)`, deserialize
- `feedback.review_formalize` → read formulation from S3, filter, write back to S3
- `web_feedback.review_formalize` → same pattern
- `env_spec` copy → upload to S3 as `research/{run_id}/env_spec.json`
- Validation file deletion (`router.py`) → `storage.delete(...)`

## Acceptance Criteria

- [ ] AC1: `decisionlab run "problem"` creates a Run record in Postgres with UUID
- [ ] AC2: Deep research reports appear in MinIO at `research/{run_id}/deep/{slug}.md`
- [ ] AC3: Summary report appears in MinIO at `research/{run_id}/report.md`
- [ ] AC4: Formulations appear in MinIO at `research/{run_id}/formulations/{slug}.md`
- [ ] AC5: Reasoner specs appear in MinIO at `models/{run_id}/reasoner/{fid}.json`
- [ ] AC6: Builder models appear in MinIO at `models/{run_id}/builder/{fid}_model.py`
- [ ] AC7: Builder tests run successfully from temp dir after S3 download
- [ ] AC8: Pipeline state saves to and loads from S3 (resume works)
- [ ] AC9: Feedback formulation filtering reads from and writes to S3
- [ ] AC10: All artifacts are registered in the `artifacts` table with correct types
- [ ] AC11: No file writes to local filesystem except temp dirs (cleaned up after use)

## Technical Notes

- Phase 1 file I/O surfaces:
  - `tools/reports.py` — `save_deep_report`, `save_summary_report`, `generate_tree_map`, `create_read_report`
  - `tools/files.py` — `create_write_file`, `create_read_file` (LLM-callable tools used by Formalizer, Reasoner, Builder)
  - `router.py` — `PipelineState.save()`, validation file deletion
  - `feedback.py` / `web_feedback.py` — formulation filtering overwrites
  - `cli.py` — `shutil.copy2` for env_spec, `_reports_dir()` path construction
  - `server.py` — `reports_dir` construction
- The `create_write_file` / `create_read_file` tool factory pattern in `files.py` is the single choke point for all LLM-initiated I/O
- Builder's pytest execution requires local files — use `tempfile.mkdtemp()`, download from S3, run tests, delete temp dir

## Decisions

| Decision | Rationale |
|----------|-----------|
| `run_id` replaces `reports_dir` | S3 doesn't have directories; prefix-based organization is idiomatic |
| Builder pytest via temp dir | pytest needs local `.py` files; download → test → cleanup is the minimal local I/O |
| Artifact registration inline (not batch) | Each write immediately registers in `artifacts` table — no dangling S3 objects |

# Phase 5: Slug-based Pipeline Wiring

> Status: current | Created: 2026-04-14 | Last updated: 2026-04-15 (P5-004 done)
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Replace the T-P-F hierarchical ID system (T01-P01-F01) with slug-based naming everywhere. S3 paths use human-readable slugs; DB records use UUID primary keys. Wire model registration into the live pipeline so Phase 2 can discover models without a migration script.

## Requirements

### R1: Models table restructure
Change `models` PK from `formulation_id` (string) to `id` (UUID). Add `paradigm` and `formulation` slug columns. Unique constraint on `(run_id, paradigm, formulation)`.

### R2: Remove IdRegistry and T-P-F IDs
Delete `id_registry.py`. Remove all T-P-F ID generation, assignment, and lookup from `PipelineState` and `Router`. `selected_formulations` and `approved_specs` use slug-based values. Tree map uses paradigm/formulation names directly.

### R3: Slug-based S3 paths for agents
Reasoner writes to `reasoner/{paradigm_slug}/{formulation_slug}.json`. Builder reads from that path and writes to `builder/{paradigm_slug}/{formulation_slug}_model.py`. Router validates filenames after agent writes and auto-renames on mismatch. Re-run logic indexes by paradigm slug, no prefix parsing.

### R4: Model registration at approval
When user approves builds in `_review_build`, insert `Model` rows in Postgres. Extract `class_name` from the Python source. At pipeline completion, populate `runs.s3_report_key`.

### R5: Phase 2 model_loader update
`discover_models()` reads the new schema (UUID PK, paradigm + formulation slugs). `ModelInfo` updated. Orchestrator model selection works with new fields.

## Acceptance Criteria
- [x] `models` table has UUID PK, `paradigm` + `formulation` slug columns, unique constraint on `(run_id, paradigm, formulation)`
- [x] `id_registry.py` deleted, no T-P-F IDs generated anywhere
- [x] `PipelineState` has no `ids` field, no `topic_id`; `selected_formulations` and `approved_specs` use slug values
- [x] S3 paths: `reasoner/{paradigm}/{formulation}.json`, `builder/{paradigm}/{formulation}_model.py`
- [x] Router validates agent filenames after write, auto-renames mismatches
- [x] Approved models are inserted into `models` table at REVIEW_BUILD
- [x] `runs.s3_report_key` populated at pipeline completion
- [ ] Phase 2 `discover_models()` returns models from live pipeline runs
- [ ] All existing tests pass (updated for new API)

## Technical Notes
- `slugify()` already exists in `tools/reports.py` — reuse for formulation name → slug conversion
- `_convert_formulations_to_ids` becomes `_convert_formulations_to_slugs` — just slugifies names, no registry
- Re-run filtering in `_review_build` / `_execute_rerun_cascade` simplifies from `startswith(paradigm_id + "-")` to direct dict key lookup
- `write_file` tool doesn't need changes — LLM provides the relative path, Router validates after

## Decisions
- T-P-F IDs dropped entirely — slugs for S3, UUIDs for DB
- `topic_id` concept removed — run_id (UUID) is the only run identifier
- Model registration happens at approval (REVIEW_BUILD), not at write time (BUILD)
- Formulation slug collisions handled with `-2` suffix (same paradigm, same slugified name)

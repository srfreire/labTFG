---
id: P3-002
title: Migrate model loader and orchestrator model calls to S3 + Postgres
status: done
kind: strike
phase: 3
heat: core
priority: 2
blocked_by: [P3-001]
created: 2026-04-11
updated: 2026-04-11
---

# P3-002: Migrate model loader and orchestrator model calls to S3 + Postgres

## Objective
Replace filesystem-based model discovery with Postgres queries and S3-based model loading.

## Requirements
- `discover_models()` in `model_loader.py`:
  - Remove `builder_dir.glob("*_model.py")` filesystem scan
  - Query Postgres `models` table for all registered models
  - Return `ModelInfo` objects constructed from DB rows (with `s3_model_key` instead of `file_path`)
  - Remove `init_db()` and `register_model()` calls (Phase 1 handles registration now)
- `load_model(model_info, seed)` in `model_loader.py`:
  - Download `*_model.py` from S3 via `storage.get(model_info.s3_model_key)`
  - Write to `tempfile.mkdtemp()` for importlib loading
  - `importlib.util.spec_from_file_location(module_name, temp_path)`
  - Apply seed replacement as before
  - Track temp dirs for cleanup after experiment
- `ModelInfo` dataclass:
  - Replace `file_path: str` with `s3_model_key: str`
  - Keep `formulation_id`, `class_name`, `paradigm`, `description`
- Update Orchestrator call sites:
  - `list_available_models` tool → call updated `discover_models()`
  - `run_simulation` tool → call updated `load_model()`
  - Present available `run_id`s to user so they can pick which Phase 1 run's models to use

## Acceptance Criteria
- [x] `discover_models()` returns models from Postgres, not filesystem
- [x] `load_model()` downloads from S3, loads via importlib, model executes correctly
- [x] Seed-based RNG isolation still works (deterministic runs)
- [x] No filesystem glob or hardcoded path in model_loader.py
- [x] Orchestrator's `list_available_models` works with new discover_models
- [x] Orchestrator's `run_simulation` works with new load_model
- [x] Temp dirs cleaned up after experiment ends

## Files Likely Affected
- `phase2-juan/simlab/model_loader.py` — discover_models, load_model, ModelInfo
- `phase2-juan/simlab/orchestrator.py` — list_available_models, run_simulation call sites

## Context
Phase spec: `docs/specs/infrastructure/phase-3-phase2-integration.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `core`

## Completion Summary

**Commit:** `c03f1db` — `feat[phase2]: migrate model loader, reporter, charts to S3 (P3-002, P3-004)`

### What was built
- `discover_models()` queries Postgres `models` table instead of filesystem glob
- `load_model()` downloads from S3 via `storage.get`, loads via importlib from tempdir
- `ModelInfo` dataclass uses `s3_model_key` instead of `file_path`
- Orchestrator's `list_available_models` and `run_simulation` tools updated for new API
- Temp dirs tracked and cleaned up after experiment

### Files created/modified
- `phase2-juan/simlab/model_loader.py` — discover_models, load_model, ModelInfo rewrite
- `phase2-juan/simlab/orchestrator.py` — updated call sites

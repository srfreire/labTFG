---
id: P3-001
title: Bootstrap shared infrastructure in Phase 2 API
status: done
kind: strike
phase: 3
heat: bootstrap
priority: 1
blocked_by: [P1-006]
created: 2026-04-11
updated: 2026-04-11
---

# P3-001: Bootstrap shared infrastructure in Phase 2 API

## Objective
Initialize shared infrastructure (MinIO + Postgres) in the FastAPI app lifecycle and remove filesystem path configuration.

## Requirements
- Remove `RESEARCH_DIR`, `OUTPUT_DIR`, `BUILDER_DIR` path variables from `api.py`
- Remove `_env_path()` helper function
- Add FastAPI lifespan handler:
  - On startup: `await shared.init()`
  - On shutdown: `await shared.shutdown()`
- Update `Orchestrator` constructor:
  - Remove `research_dir`, `output_dir`, `builder_dir` Path parameters
  - Accept `storage: StorageService` and `db: DatabaseService` instead (or access via `shared.storage` / `shared.db`)
- Update WebSocket handler to pass new params to Orchestrator
- Remove the `api.py` monkey-patching of `Orchestrator._build_tools()` path parameters if they reference filesystem paths

## Acceptance Criteria
- [x] FastAPI app starts with `shared.init()`, shuts down with `shared.shutdown()`
- [x] No `RESEARCH_DIR`, `OUTPUT_DIR`, `BUILDER_DIR` variables in `api.py`
- [x] Orchestrator accepts storage/db services instead of filesystem paths
- [x] WebSocket connection still works (Orchestrator instantiation succeeds)
- [x] Health endpoint still returns `{"status": "ok"}`

## Files Likely Affected
- `phase2-juan/simlab/api.py` — path config removal, lifespan handler, Orchestrator construction
- `phase2-juan/simlab/orchestrator.py` — constructor signature change

## Context
Phase spec: `docs/specs/infrastructure/phase-3-phase2-integration.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `bootstrap`

## Completion Summary

**Commit:** `e84c030` — `feat[phase2]: bootstrap shared.init in API, remove path config (P3-001)`

### What was built
- Added FastAPI lifespan handler with `shared.init()` on startup and `shared.shutdown()` on shutdown
- Removed `RESEARCH_DIR`, `OUTPUT_DIR`, `BUILDER_DIR` path variables from api.py
- Updated Orchestrator constructor to use `shared.storage`/`shared.db` instead of filesystem paths
- Updated WebSocket handler to pass new params

### Files created/modified
- `phase2-juan/simlab/api.py` — lifespan handler, path config removal
- `phase2-juan/simlab/orchestrator.py` — constructor signature change

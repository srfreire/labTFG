---
id: P4-002
title: Create Dockerfile for Phase 2 server
status: done
kind: strike
phase: 4
heat: containers
priority: 1
blocked_by: [P3-003, P3-004]
created: 2026-04-11
updated: 2026-04-11
---

# P4-002: Create Dockerfile for Phase 2 server

## Objective
Containerize the Phase 2 FastAPI/WebSocket server with all dependencies including shared package and tectonic LaTeX compiler.

## Requirements
- Multi-stage Dockerfile at `phase2-juan/Dockerfile`
- Builder stage:
  - Base: `python:3.12-slim`
  - Install `uv`
  - Copy `shared/` package and `phase2-juan/simlab/` source
  - `uv sync` to install all dependencies including shared
- Runtime stage:
  - Base: `python:3.12-slim`
  - Install `tectonic` binary (download pre-built from GitHub releases or build via cargo)
  - Copy virtual env from builder
  - Copy `simlab/templates/` (LaTeX template)
  - Expose port 8000
  - Entrypoint: `uvicorn simlab.api:app --host 0.0.0.0 --port 8000`
- Environment variables:
  - `ANTHROPIC_API_KEY`
  - `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`
  - `POSTGRES_DSN`
- `.dockerignore` for Phase 2 (exclude `.venv`, `__pycache__`, `web/`, `output/`, `.env`, `node_modules/`)

## Acceptance Criteria
- [x] `docker build -t labtfg-phase2 phase2-juan/` builds without errors
- [x] Container starts and Phase 2 WebSocket server is accessible on port 8000
- [x] `tectonic` is available in the container (`tectonic --version` works)
- [x] Container can connect to MinIO and Postgres
- [x] `.dockerignore` excludes irrelevant files

## Files Likely Affected
- `phase2-juan/Dockerfile` — new file
- `phase2-juan/.dockerignore` — new file

## Context
Phase spec: `docs/specs/infrastructure/phase-4-containerization.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `containers`

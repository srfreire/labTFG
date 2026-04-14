---
id: P4-001
title: Create Dockerfile for Phase 1 server
status: done
kind: strike
phase: 4
heat: containers
priority: 1
blocked_by: [P2-004]
created: 2026-04-11
updated: 2026-04-11
---

# P4-001: Create Dockerfile for Phase 1 server

## Objective
Containerize the Phase 1 FastAPI/WebSocket server with all dependencies including the shared package.

## Requirements
- Multi-stage Dockerfile at `phase1-pablo/Dockerfile`
- Builder stage:
  - Base: `python:3.12-slim`
  - Install `uv` via `pip install uv` or `curl`
  - Copy `shared/` package and `phase1-pablo/` source
  - `uv sync` to install all dependencies including shared
- Runtime stage:
  - Base: `python:3.12-slim`
  - Copy virtual env from builder
  - Expose port 8001
  - Entrypoint: `uvicorn decisionlab.server:app --host 0.0.0.0 --port 8001`
- Environment variables (all with no defaults — must be provided):
  - `ANTHROPIC_API_KEY`
  - `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`
  - `POSTGRES_DSN`
- `.dockerignore` for Phase 1 (exclude `.venv`, `__pycache__`, `examples/`, `.env`, `node_modules/`)

## Acceptance Criteria
- [x] `docker build -t labtfg-phase1 phase1-pablo/` builds without errors
- [x] Container starts and Phase 1 WebSocket server is accessible on port 8001
- [x] Container can connect to MinIO and Postgres (when running in docker-compose network)
- [x] `.dockerignore` excludes irrelevant files

## Files Likely Affected
- `phase1-pablo/Dockerfile` — new file
- `phase1-pablo/.dockerignore` — new file

## Context
Phase spec: `docs/specs/infrastructure/phase-4-containerization.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `containers`

## Completion Summary

**Commit:** `bf79b25` — `feat[infra]: add Dockerfiles for all services (P4-001, P4-002, P4-003)`

### What was built
- Multi-stage Dockerfile for Phase 1 server (python:3.12-slim base, uv sync, uvicorn entrypoint on port 8001)
- .dockerignore at repo root excluding .venv, __pycache__, examples, .env, node_modules

### Files created
- `phase1-pablo/Dockerfile` — multi-stage build
- `.dockerignore` — repo-level ignores

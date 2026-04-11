---
id: P4-001
title: Create Dockerfile for Phase 1 server
status: in-progress
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
- [ ] `docker build -t labtfg-phase1 phase1-pablo/` builds without errors
- [ ] Container starts and Phase 1 WebSocket server is accessible on port 8001
- [ ] Container can connect to MinIO and Postgres (when running in docker-compose network)
- [ ] `.dockerignore` excludes irrelevant files

## Files Likely Affected
- `phase1-pablo/Dockerfile` — new file
- `phase1-pablo/.dockerignore` — new file

## Context
Phase spec: `docs/specs/infrastructure/phase-4-containerization.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `containers`

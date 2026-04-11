# Phase 4: Containerization

> Status: current | Created: 2026-04-11 | Last updated: 2026-04-11
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Containerize all application services (Phase 1 server, Phase 2 server, Phase 2 web frontend) and complete the docker-compose stack so the entire system boots with a single `docker-compose up`. Include a data migration script to seed MinIO with existing sample-run artifacts.

## Requirements

### R1: Dockerfile for Phase 1 server

- Multi-stage build: dependency install → app copy
- Base: Python 3.12 slim
- Package manager: uv (install in builder stage)
- Install `shared` package as local dependency
- Entrypoint: `uvicorn decisionlab.server:app --host 0.0.0.0 --port 8001`
- Env vars: `ANTHROPIC_API_KEY`, MinIO/Postgres vars from shared settings

### R2: Dockerfile for Phase 2 server

- Multi-stage build: dependency install → app copy
- Base: Python 3.12 slim
- Install `tectonic` for PDF compilation (or use a stage with tectonic pre-installed)
- Install `shared` package as local dependency
- Entrypoint: `uvicorn simlab.api:app --host 0.0.0.0 --port 8000`
- Env vars: `ANTHROPIC_API_KEY`, MinIO/Postgres vars from shared settings

### R3: Dockerfile for Phase 2 web frontend

- Multi-stage build: pnpm install + Vite build → nginx serve
- Build stage: Node 22 + pnpm
- Serve stage: nginx:alpine with custom config
- Nginx config: serve static files, proxy `/ws` to Phase 2 server, proxy `/api` to Phase 2 server

### R4: Complete docker-compose stack

- Add Phase 1 server, Phase 2 server, Phase 2 web frontend to existing docker-compose (which has MinIO + Postgres from P1-001)
- Service dependency ordering: app services depend on MinIO + Postgres being healthy
- Shared network for all services
- Environment variable passthrough from `.env` file
- Port mapping: web frontend on 5173 (or 80), Phase 2 API on 8000, Phase 1 API on 8001, MinIO console on 9001
- Update `.env.example` with all service vars

### R5: Data migration script

- Python script to upload existing `phase1-pablo/examples/sample-run/` to MinIO
- Creates a Run record in Postgres for the sample data
- Uploads all artifacts (reports, formulations, models, tests) under the new run_id prefix
- Registers models in `models` table, artifacts in `artifacts` table
- Idempotent: safe to run multiple times

## Acceptance Criteria

- [ ] AC1: `docker-compose up` boots all 5 services (MinIO, Postgres, Phase 1, Phase 2, Web)
- [ ] AC2: Phase 2 web frontend accessible at `localhost:5173`
- [ ] AC3: Phase 2 API WebSocket works through nginx proxy
- [ ] AC4: Phase 1 server accessible at `localhost:8001`
- [ ] AC5: Migration script uploads sample-run data to MinIO and registers in Postgres
- [ ] AC6: After migration, Phase 2 can discover and use the sample-run models
- [ ] AC7: Full pipeline works containerized: Phase 2 web → chat → simulate → report
- [ ] AC8: `docker-compose down && docker-compose up` preserves data (volumes)
- [ ] AC9: All containers build without errors from clean state

## Technical Notes

- Phase 1 uses `uv` as package manager, Phase 2 uses `uv`, web uses `pnpm`
- `shared` package is a local dependency for both Python services — copy it into both container builds
- `tectonic` is a Rust-based LaTeX compiler — install via `curl` or use a pre-built binary in the Docker image
- The web frontend's Vite proxy config (`vite.config.ts`) is only for dev; in production, nginx handles proxying
- Both Python apps need the shared settings env vars to point to container service names (e.g. `minio:9000` not `localhost:9000`)

## Decisions

| Decision | Rationale |
|----------|-----------|
| Nginx for frontend serving | Industry standard, handles static files + proxy in one process |
| Separate ports for Phase 1 and Phase 2 servers | They're independent services, no reason to share a port |
| Migration script (not auto-migration on startup) | One-time operation, should be explicit, idempotent |
| uv in Docker | Matches dev workflow, fast installs, lockfile support |

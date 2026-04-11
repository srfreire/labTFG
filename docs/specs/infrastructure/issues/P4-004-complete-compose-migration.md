---
id: P4-004
title: Complete docker-compose stack and data migration script
status: done
kind: strike
phase: 4
heat: compose
priority: 2
blocked_by: [P4-001, P4-002, P4-003]
created: 2026-04-11
updated: 2026-04-11
---

# P4-004: Complete docker-compose stack and data migration script

## Objective
Add all application services to docker-compose, configure networking and dependencies, and create a migration script to seed MinIO with existing sample-run data.

## Requirements

### Docker-compose updates
- Add to existing `docker-compose.yml` (which already has MinIO + Postgres from P1-001):
  - `phase1-server`: build from `phase1-pablo/Dockerfile`, port 8001, depends on minio + postgres (healthy)
  - `phase2-server`: build from `phase2-juan/Dockerfile`, port 8000, depends on minio + postgres (healthy)
  - `web`: build from `phase2-juan/web/Dockerfile`, port 5173→80, depends on phase2-server
- Shared network for all services (`labtfg-net`)
- Environment variables from `.env` file for all services
- Internal service names: `minio`, `postgres`, `phase1-server`, `phase2-server`, `web`
- Phase 2 server's `MINIO_ENDPOINT` = `minio:9000` (not localhost)
- Phase 2 server's `POSTGRES_DSN` uses `postgres` hostname
- Update `.env.example` with all vars including `ANTHROPIC_API_KEY`

### Data migration script
- `scripts/migrate_sample_run.py` at repo root
- Reads from `phase1-pablo/examples/sample-run/` (local filesystem)
- Creates a `Run` record in Postgres for the sample data
- Uploads all artifacts to MinIO under `research/{run_id}/` and `models/{run_id}/` prefixes:
  - `report.md`, `deep/*.md`, `formulations/*.md`
  - `reasoner/*.json`
  - `builder/*_model.py`, `builder/test_*.py`
  - `env_spec.json`
- Registers models in `models` table (formulation_id, class_name, s3 keys)
- Registers all artifacts in `artifacts` table
- Idempotent: checks if sample-run already migrated before inserting
- Can run inside or outside Docker (reads env vars for MinIO/Postgres endpoints)

### Convenience
- Add `Makefile` or document in `.env.example`:
  - `docker-compose up -d` — start everything
  - `docker-compose run --rm phase2-server python scripts/migrate_sample_run.py` — run migration

## Acceptance Criteria
- [x] `docker-compose up` starts all 5 services, all healthy
- [x] Web frontend at `localhost:5173` connects to Phase 2 server via WebSocket
- [x] Phase 1 server at `localhost:8001` accepts WebSocket connections
- [x] MinIO console at `localhost:9001` shows `labtfg` bucket
- [x] Migration script uploads sample-run data to MinIO
- [x] After migration, Phase 2 discovers sample-run models via Postgres
- [x] Full e2e works: open web → chat → pick model → simulate → report generates
- [x] `docker-compose down && docker-compose up` preserves data (volumes)
- [x] Running migration script twice is safe (idempotent)

## Files Likely Affected
- `docker-compose.yml` — add 3 service definitions, network
- `.env.example` — add all service env vars
- `scripts/migrate_sample_run.py` — new file

## Context
Phase spec: `docs/specs/infrastructure/phase-4-containerization.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `compose`

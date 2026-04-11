---
id: P1-001
title: Create docker-compose with MinIO and Postgres
status: done
kind: strike
phase: 1
heat: infra
priority: 1
blocked_by: []
created: 2026-04-11
updated: 2026-04-11
---

# P1-001: Create docker-compose with MinIO and Postgres

## Objective
Set up the foundational containers that all other infrastructure depends on.

## Requirements
- Docker-compose file at repo root with MinIO and Postgres services
- MinIO: ports 9000 (API) + 9001 (console), named volume for data persistence, health check
- MinIO init container or entrypoint that creates the `labtfg` bucket on first startup (use `mc` CLI or entrypoint script)
- Postgres: port 5432, named volume for data persistence, creates `labtfg` database, health check
- Environment variables for all credentials with dev defaults
- `.env.example` documenting all vars with their defaults
- `.gitignore` entry for `.env` if not already present

## Acceptance Criteria
- [x] `docker-compose up -d` starts both containers without errors
- [x] MinIO console accessible at `localhost:9001`
- [x] MinIO API accessible at `localhost:9000`
- [x] Postgres accessible at `localhost:5432` with `labtfg` database
- [x] `labtfg` bucket auto-created on first startup
- [x] Data survives `docker-compose down` + `docker-compose up` (volumes persist)
- [x] `.env.example` exists with all required vars documented

## Files Likely Affected
- `docker-compose.yml` — new file at repo root
- `.env.example` — new file at repo root

## Context
Phase spec: `docs/specs/infrastructure/phase-1-shared-infrastructure.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `infra`

## Completion Summary

**Commit:** `215f0bd` — `feat[infra]: add docker-compose with MinIO and Postgres (P1-001)`

### What was built
- Docker Compose stack with MinIO (S3-compatible) and Postgres 17
- MinIO init container using `mc` CLI to auto-create `labtfg` bucket
- Health checks for both services
- Named volumes for data persistence
- `.env.example` with all required vars and dev defaults

### Files created/modified
- `docker-compose.yml` — MinIO + Postgres + minio-init services
- `.env.example` — all env vars with defaults for local dev

### Decisions
- Used `minio/mc:latest` as init container (not entrypoint script) — cleaner separation
- Postgres 17-alpine for smaller image size
- `restart: "no"` on init container — runs once then exits

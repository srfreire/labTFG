---
id: P1-001
title: Create docker-compose with MinIO and Postgres
status: in-progress
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
- [ ] `docker-compose up -d` starts both containers without errors
- [ ] MinIO console accessible at `localhost:9001`
- [ ] MinIO API accessible at `localhost:9000`
- [ ] Postgres accessible at `localhost:5432` with `labtfg` database
- [ ] `labtfg` bucket auto-created on first startup
- [ ] Data survives `docker-compose down` + `docker-compose up` (volumes persist)
- [ ] `.env.example` exists with all required vars documented

## Files Likely Affected
- `docker-compose.yml` — new file at repo root
- `.env.example` — new file at repo root

## Context
Phase spec: `docs/specs/infrastructure/phase-1-shared-infrastructure.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `infra`

---
id: P1-002
title: Create settings module with env var config
status: todo
kind: strike
phase: 1
heat: infra
priority: 1
blocked_by: [P1-001]
created: 2026-04-11
updated: 2026-04-11
---

# P1-002: Create settings module with env var config

## Objective
Centralize all infrastructure configuration in a single Settings dataclass read from environment variables.

## Requirements
- `shared/shared/settings.py` with a `Settings` dataclass
- Fields: `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `POSTGRES_DSN`
- Defaults matching docker-compose dev values (e.g. `localhost:9000`, `minioadmin`, `postgresql+asyncpg://postgres:postgres@localhost:5432/labtfg`)
- Factory function `load_settings() -> Settings` that reads from `os.environ` with fallback to defaults
- No third-party config libs — just `os.environ.get()` and a dataclass
- Add `python-dotenv` to `shared` dependencies for `.env` file loading (optional, loaded if present)

## Acceptance Criteria
- [ ] `load_settings()` returns defaults when no env vars set
- [ ] `load_settings()` picks up env var overrides
- [ ] `Settings` is a frozen dataclass (immutable after creation)
- [ ] All fields match what docker-compose exposes

## Files Likely Affected
- `shared/shared/settings.py` — new file
- `shared/pyproject.toml` — add `python-dotenv` dependency

## Context
Phase spec: `docs/specs/infrastructure/phase-1-shared-infrastructure.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `infra`

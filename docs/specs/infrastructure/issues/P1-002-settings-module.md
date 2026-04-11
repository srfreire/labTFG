---
id: P1-002
title: Create settings module with env var config
status: done
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
- [x] `load_settings()` returns defaults when no env vars set
- [x] `load_settings()` picks up env var overrides
- [x] `Settings` is a frozen dataclass (immutable after creation)
- [x] All fields match what docker-compose exposes

## Files Likely Affected
- `shared/shared/settings.py` — new file
- `shared/pyproject.toml` — add `python-dotenv` dependency

## Context
Phase spec: `docs/specs/infrastructure/phase-1-shared-infrastructure.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `infra`

## Completion Summary

**Commit:** `97cbda6` — `feat[shared]: add settings module with env var config (P1-002)`

### What was built
- `Settings` frozen dataclass with all MinIO + Postgres fields
- `load_settings()` reads env vars with dev defaults, optional dotenv support
- 3 tests covering defaults, overrides, and immutability

### Files created/modified
- `shared/shared/settings.py` — Settings dataclass + load_settings()
- `shared/pyproject.toml` — added python-dotenv dependency
- `shared/tests/test_settings.py` — 3 tests

### Decisions
- POSTGRES_DSN default uses `labtfg:labtfg` (matching docker-compose), not `postgres:postgres` as originally in spec

---
id: P1-004
title: Define SQLAlchemy async models for all tables
status: done
kind: strike
phase: 1
heat: database
priority: 2
blocked_by: [P1-002]
created: 2026-04-11
updated: 2026-04-11
---

# P1-004: Define SQLAlchemy async models for all tables

## Objective
Define the 4 Postgres tables as SQLAlchemy 2.0 declarative models with async engine and session management.

## Requirements

### Models (`shared/shared/models.py`)
- `Base` declarative base
- `Run` — id (UUID PK, server_default uuid_generate_v4), created_at, problem_description, status, s3_report_key, s3_prefix
- `Model` — formulation_id (string PK), class_name, paradigm, description, run_id (FK → runs.id nullable), s3_model_key, s3_test_key, registered_at, metadata (JSONB)
- `Experiment` — id (UUID PK), created_at, updated_at (auto-update), description, status, spec (JSONB), models_used (JSONB), steps, seed, s3_events_key, s3_replay_key, s3_tracker_key, s3_analyst_key, s3_pdf_key, s3_tex_key, s3_charts_prefix
- `Artifact` — id (UUID PK), s3_key (unique), artifact_type, run_id (FK nullable), experiment_id (FK nullable), created_at, size_bytes, content_type
- Proper FK relationships with `relationship()` where useful (Run.models, Run.artifacts, Experiment.artifacts)

### Database service (`shared/shared/database.py`)
- `create_engine(dsn)` → `AsyncEngine` with pool_size=5, max_overflow=10
- `create_session_factory(engine)` → `async_sessionmaker`
- `get_session()` async context manager yielding `AsyncSession`
- `DatabaseService` class holding engine + session factory, with `connect()` and `close()` methods

### Dependencies
- Add `sqlalchemy[asyncio]`, `asyncpg` to `shared/pyproject.toml`

## Acceptance Criteria
- [x] All 4 models importable from `shared.models`
- [x] FKs correctly defined (Model.run_id → Run.id, Artifact.run_id → Run.id, Artifact.experiment_id → Experiment.id)
- [x] `DatabaseService.connect()` creates engine and verifies connectivity
- [x] `get_session()` yields async sessions that can insert/query all 4 tables
- [x] JSONB columns accept and return Python dicts
- [x] UUID PKs auto-generate when not provided

## Files Likely Affected
- `shared/shared/models.py` — new file
- `shared/shared/database.py` — new file
- `shared/pyproject.toml` — add `sqlalchemy[asyncio]`, `asyncpg`

## Context
Phase spec: `docs/specs/infrastructure/phase-1-shared-infrastructure.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `database`

## Completion Summary

**Commit:** `ec81e42` — `feat[shared]: define SQLAlchemy models and DatabaseService (P1-004)`

### What was built
- SQLAlchemy 2.0 declarative models: Run, Model, Experiment, Artifact with FKs and relationships
- DatabaseService with async engine, session factory, get_session() context manager
- 6 integration tests against Postgres

### Files created/modified
- `shared/shared/models.py` — 4 SQLAlchemy models with JSONB, UUID PKs, FKs
- `shared/shared/database.py` — DatabaseService class
- `shared/pyproject.toml` — added sqlalchemy[asyncio], asyncpg
- `shared/tests/test_database.py` — 6 integration tests

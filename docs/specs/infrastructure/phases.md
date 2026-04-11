# Infrastructure — Phase Breakdown

> Status: forged | Created: 2026-04-11 | Last updated: 2026-04-11
> References: [general.md](general.md)

## Phases

- [x] **Phase 1: Shared Infrastructure Layer** — StorageService (MinIO), DatabaseService (async Postgres + SQLAlchemy), Alembic migrations, shared.init() lifecycle, docker-compose with MinIO + Postgres
  - Dependencies: none
  - Issues: P1-001, P1-002, P1-003, P1-004, P1-005, P1-006
  - Heats: infra (P1-001→P1-002), storage (P1-003), database (P1-004→P1-005), lifecycle (P1-006)

- [x] **Phase 2: Phase 1 Integration** — Modify Phase 1 tool functions to use StorageService, add run_id to pipeline, register artifacts in DB
  - Dependencies: Phase 1
  - Issues: P2-001, P2-002, P2-003, P2-004
  - Heats: pipeline (P2-001→P2-004), tools (P2-002, P2-003 parallel)

- [x] **Phase 3: Phase 2 Integration** — Modify model_loader, orchestrator, reporter, api.py to read from MinIO/Postgres, update experiment lifecycle with S3 keys
  - Dependencies: Phase 1 (parallel with Phase 2)
  - Issues: P3-001, P3-002, P3-003, P3-004
  - Heats: bootstrap (P3-001), core (P3-002→P3-003), output (P3-004 parallel)

- [x] **Phase 4: Containerization** — Dockerfiles for all services, complete docker-compose stack, data migration script
  - Dependencies: Phase 2, Phase 3
  - Issues: P4-001, P4-002, P4-003, P4-004
  - Heats: containers (P4-001, P4-002, P4-003 parallel), compose (P4-004)

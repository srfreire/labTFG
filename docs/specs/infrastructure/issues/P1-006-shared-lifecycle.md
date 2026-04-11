---
id: P1-006
title: Implement shared.init() and shutdown() lifecycle
status: todo
kind: strike
phase: 1
heat: lifecycle
priority: 4
blocked_by: [P1-003, P1-005]
created: 2026-04-11
updated: 2026-04-11
---

# P1-006: Implement shared.init() and shutdown() lifecycle

## Objective
Single entry point to boot and tear down all infrastructure services, exposing module-level singletons for storage and database access.

## Requirements
- Update `shared/shared/__init__.py`:
  - `async init(settings: Settings | None = None)` — if no settings passed, call `load_settings()`; create `DatabaseService`, call `connect()`; create `StorageService`, call `connect()`; store as module-level `storage` and `db` attributes
  - `async shutdown()` — call `close()` on both services, set module attrs to None
  - Module-level `storage: StorageService | None` and `db: DatabaseService | None` (None before init)
- Keep existing `store.py` untouched — mark its functions with `# deprecated: use shared.db` comments
- Verify that `import shared; await shared.init()` then `shared.storage.put(...)` and `shared.db.get_session()` work end-to-end

## Acceptance Criteria
- [ ] `await shared.init()` boots both services without errors (MinIO + Postgres reachable)
- [ ] `shared.storage` is a usable `StorageService` after init
- [ ] `shared.db` is a usable `DatabaseService` after init
- [ ] `await shared.shutdown()` closes cleanly, no resource leaks
- [ ] Calling `shared.storage` before `init()` is None (not a crash)
- [ ] Existing `store.py` functions still work independently (backward compat)

## Files Likely Affected
- `shared/shared/__init__.py` — rewrite (currently empty)

## Context
Phase spec: `docs/specs/infrastructure/phase-1-shared-infrastructure.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `lifecycle`

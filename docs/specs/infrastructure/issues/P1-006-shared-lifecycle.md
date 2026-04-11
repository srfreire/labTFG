---
id: P1-006
title: Implement shared.init() and shutdown() lifecycle
status: done
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
- [x] `await shared.init()` boots both services without errors (MinIO + Postgres reachable)
- [x] `shared.storage` is a usable `StorageService` after init
- [x] `shared.db` is a usable `DatabaseService` after init
- [x] `await shared.shutdown()` closes cleanly, no resource leaks
- [x] Calling `shared.storage` before `init()` is None (not a crash)
- [x] Existing `store.py` functions still work independently (backward compat)

## Files Likely Affected
- `shared/shared/__init__.py` — rewrite (currently empty)

## Context
Phase spec: `docs/specs/infrastructure/phase-1-shared-infrastructure.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `lifecycle`

## Completion Summary

**Commit:** `2524885` — `feat[shared]: implement init/shutdown lifecycle (P1-006)`

### What was built
- `shared.init()` boots StorageService + DatabaseService from settings
- `shared.shutdown()` tears down cleanly, sets singletons to None
- Module-level `shared.storage` and `shared.db` singletons
- 6 tests covering lifecycle, functionality, and backward compat with store.py

### Files created/modified
- `shared/shared/__init__.py` — init/shutdown + singletons
- `shared/tests/test_lifecycle.py` — 6 tests

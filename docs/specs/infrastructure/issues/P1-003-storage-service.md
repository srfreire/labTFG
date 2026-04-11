---
id: P1-003
title: Implement StorageService with aioboto3
status: done
kind: strike
phase: 1
heat: storage
priority: 2
blocked_by: [P1-002]
created: 2026-04-11
updated: 2026-04-11
---

# P1-003: Implement StorageService with aioboto3

## Objective
Async S3 client wrapping aioboto3 that both phases will use for all artifact I/O.

## Requirements
- `shared/shared/storage.py` with `StorageService` class
- Constructor takes `Settings` (endpoint, credentials, bucket)
- Methods:
  - `async put(key: str, data: bytes, content_type: str = "application/octet-stream") -> str` — upload, return key
  - `async get(key: str) -> bytes` — download
  - `async put_text(key: str, text: str, content_type: str = "text/plain") -> str` — convenience for UTF-8 strings
  - `async get_text(key: str) -> str` — convenience for UTF-8 strings
  - `async list(prefix: str) -> list[str]` — list keys under prefix
  - `async delete(key: str) -> None` — remove object
  - `async exists(key: str) -> bool` — check existence
- `async connect()` — create aioboto3 session + verify bucket exists
- `async close()` — clean up session/client
- Add `aioboto3` to `shared/pyproject.toml` dependencies

## Acceptance Criteria
- [x] `put()` + `get()` round-trips arbitrary bytes
- [x] `put_text()` + `get_text()` round-trips UTF-8 strings including unicode
- [x] `list(prefix)` returns correct keys after multiple uploads with shared prefix
- [x] `delete()` removes object, `exists()` returns False after deletion
- [x] `exists()` returns True for existing keys, False for non-existent
- [x] Works against docker-compose MinIO instance

## Files Likely Affected
- `shared/shared/storage.py` — new file
- `shared/pyproject.toml` — add `aioboto3`

## Context
Phase spec: `docs/specs/infrastructure/phase-1-shared-infrastructure.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `storage`

## Completion Summary

**Commit:** `9938797` — `feat[shared]: implement StorageService with aioboto3 (P1-003)`

### What was built
- `StorageService` class with all 7 methods (put, get, put_text, get_text, list, delete, exists)
- connect/close lifecycle, aioboto3 session management
- 5 integration tests against MinIO

### Files created/modified
- `shared/shared/storage.py` — StorageService implementation
- `shared/pyproject.toml` — added aioboto3 dependency
- `shared/tests/test_storage.py` — 5 integration tests

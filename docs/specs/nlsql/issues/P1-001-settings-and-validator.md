---
id: P1-001
title: Add NLSQL settings and implement SQL validator
status: done
kind: strike
phase: 1
heat: foundation
blocked_by: []
---

# P1-001: Add NLSQL settings and implement SQL validator

## Objective

Add NLSQL configuration to shared settings and implement the static SQL
validation layer that prevents unsafe queries before execution.

## Requirements

### Settings

Add to `shared/shared/settings.py` in the `Settings` class:
- `NLSQL_MAX_S3_FETCH: int = 3` — max experiment rows to fetch S3 data for
- `NLSQL_MODEL: str = "anthropic/claude-haiku-4-5"` — model for plan + synthesize calls

Both overridable via environment variables (follow existing `load_settings` pattern).

### SQL Validator

Create `phase2-juan/simlab/nlsql.py` with a `validate_sql(sql: str)` function:

1. Parse with `sqlparse.parse()` — must produce exactly 1 statement
2. Statement type must be `SELECT` (reject INSERT/UPDATE/DELETE/DROP/ALTER)
3. Referenced tables must be in allowlist: `{"experiments", "models", "runs"}`
4. If no `LIMIT` clause, append `LIMIT 50`
5. If `LIMIT > 50`, rewrite to `LIMIT 50`
6. Return `(validated_sql: str, error: str | None)` — error is None on success

Add `sqlparse` to `phase2-juan/pyproject.toml` dependencies.

## Acceptance Criteria

- [ ] `Settings` has `NLSQL_MAX_S3_FETCH` and `NLSQL_MODEL` with defaults
- [ ] `validate_sql` rejects non-SELECT statements
- [ ] `validate_sql` rejects queries on tables not in allowlist
- [ ] `validate_sql` enforces LIMIT 50 cap
- [ ] `sqlparse` added to dependencies

## Files Likely Affected

- `shared/shared/settings.py` — add 2 fields to Settings class
- `phase2-juan/simlab/nlsql.py` — create with validate_sql function
- `phase2-juan/pyproject.toml` — add sqlparse dependency

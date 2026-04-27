---
id: P1-004
title: Unit and integration tests for NLSQL module
status: todo
kind: strike
phase: 1
heat: tests
blocked_by: [P1-002]
---

# P1-004: Unit and integration tests for NLSQL module

## Objective

Comprehensive test coverage for the nlsql module — validator, plan parsing,
S3 fetch limits, and full pipeline roundtrip.

## Requirements

Create `phase2-juan/tests/test_nlsql.py` with:

### Validator tests
- `test_validate_select_only` — rejects INSERT, UPDATE, DELETE, DROP
- `test_validate_allowed_tables` — rejects queries on memories, artifacts, etc.
- `test_validate_limit_enforced` — adds LIMIT 50 if missing
- `test_validate_limit_capped` — rewrites LIMIT 100 to LIMIT 50
- `test_validate_valid_query` — accepts well-formed SELECT on allowed tables

### Plan tests (mock LLM)
- `test_plan_parsing` — mock LLM returns valid JSON, verify plan extraction
- `test_plan_invalid_json` — mock LLM returns garbage, verify error message

### S3 fetch tests (mock S3)
- `test_s3_fetch_respects_limit` — only fetches NLSQL_MAX_S3_FETCH rows
- `test_s3_fetch_partial_failure` — one fetch fails, others succeed
- `test_s3_fetch_truncation` — content > 4000 chars is truncated

### Integration test (mock LLM + mock Postgres + mock S3)
- `test_query_experiments_roundtrip` — full pipeline: question → plan → SQL →
  fetch → synthesize → NL answer

All tests mock external dependencies (LLM, Postgres, S3). No real infra needed.

## Acceptance Criteria

- [ ] All validator edge cases covered
- [ ] Plan parsing tested with valid and invalid LLM responses
- [ ] S3 fetch limit, partial failure, and truncation tested
- [ ] Full roundtrip integration test passes
- [ ] All tests pass with `uv run python -m pytest tests/test_nlsql.py -v`

## Files Likely Affected

- `phase2-juan/tests/test_nlsql.py` — new test file

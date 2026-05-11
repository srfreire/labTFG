"""Safety contract tests for query_history → validate_sql (sim-recall P3-004).

Locks in the rules the validator must enforce so query_history can never
mutate the DB or touch tables outside the whitelist, regardless of what
the LLM planner produces.
"""

from __future__ import annotations

import pytest
from simlab.nlsql import _MAX_LIMIT, validate_sql

# ---------------------------------------------------------------------------
# AC1 — every disallowed verb is rejected
# ---------------------------------------------------------------------------

_DISALLOWED_STATEMENTS = [
    ("INSERT", "INSERT INTO experiments (description) VALUES ('x')"),
    ("UPDATE", "UPDATE experiments SET status = 'done'"),
    ("DELETE", "DELETE FROM experiments"),
    ("DROP", "DROP TABLE experiments"),
    ("CREATE", "CREATE TABLE foo (id UUID)"),
    ("ALTER", "ALTER TABLE experiments ADD COLUMN bar INT"),
]


@pytest.mark.parametrize("verb,stmt", _DISALLOWED_STATEMENTS)
def test_disallowed_verb_is_rejected(verb: str, stmt: str):
    sql, error = validate_sql(stmt)
    assert error is not None, f"{verb} must be rejected: {stmt}"
    assert sql == ""


# ---------------------------------------------------------------------------
# AC2 — tables outside the whitelist are rejected
# ---------------------------------------------------------------------------

_DISALLOWED_TABLES = [
    "SELECT * FROM pg_user LIMIT 10",
    "SELECT * FROM nodes LIMIT 10",
    "SELECT * FROM relationships LIMIT 10",
    "SELECT * FROM artifacts LIMIT 10",
    "SELECT * FROM information_schema.tables LIMIT 10",
]


@pytest.mark.parametrize("stmt", _DISALLOWED_TABLES)
def test_non_whitelisted_table_is_rejected(stmt: str):
    sql, error = validate_sql(stmt)
    assert error is not None, f"non-whitelisted query must be rejected: {stmt}"


# ---------------------------------------------------------------------------
# AC3 — LIMIT injection + capping
# ---------------------------------------------------------------------------


def test_limit_injected_when_absent():
    sql, error = validate_sql("SELECT id FROM experiments")
    assert error is None
    assert f"LIMIT {_MAX_LIMIT}" in sql.upper()


def test_limit_capped_to_max():
    sql, error = validate_sql("SELECT id FROM experiments LIMIT 1000")
    assert error is None
    assert f"LIMIT {_MAX_LIMIT}" in sql


def test_explicit_small_limit_preserved():
    sql, error = validate_sql("SELECT id FROM experiments LIMIT 5")
    assert error is None
    assert "LIMIT 5" in sql

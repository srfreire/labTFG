"""Safety contract tests for query_history → validate_sql (sim-recall P3-004).

Locks in the rules the validator must enforce so query_history can never
mutate the DB or touch tables outside the whitelist, regardless of what
the LLM planner produces.
"""

from __future__ import annotations

import pytest
from simlab.nlsql import validate_sql

# ---------------------------------------------------------------------------
# AC1 — every disallowed verb is rejected
# ---------------------------------------------------------------------------

_ADDITIONAL_DISALLOWED_STATEMENTS = [
    ("CREATE", "CREATE TABLE foo (id UUID)"),
    ("ALTER", "ALTER TABLE experiments ADD COLUMN bar INT"),
]


@pytest.mark.parametrize("verb,stmt", _ADDITIONAL_DISALLOWED_STATEMENTS)
def test_additional_disallowed_verb_is_rejected(verb: str, stmt: str):
    sql, error = validate_sql(stmt)
    assert error is not None, f"{verb} must be rejected: {stmt}"
    assert sql == ""


# ---------------------------------------------------------------------------
# AC2 — tables outside the whitelist are rejected
# ---------------------------------------------------------------------------

_ADDITIONAL_DISALLOWED_TABLES = [
    "SELECT * FROM nodes LIMIT 10",
    "SELECT * FROM relationships LIMIT 10",
    "SELECT * FROM information_schema.tables LIMIT 10",
]


@pytest.mark.parametrize("stmt", _ADDITIONAL_DISALLOWED_TABLES)
def test_additional_non_whitelisted_table_is_rejected(stmt: str):
    sql, error = validate_sql(stmt)
    assert error is not None, f"non-whitelisted query must be rejected: {stmt}"


def test_models_used_uuid_cast_is_rejected():
    stmt = (
        "SELECT m.paradigm FROM models m "
        "LEFT JOIN experiments e "
        "ON m.id = ANY(string_to_array(e.models_used::text, ',')::uuid[])"
    )

    sql, error = validate_sql(stmt)

    assert sql == ""
    assert error is not None
    assert "models_used es JSONB" in error

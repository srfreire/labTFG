"""NLSQL — Natural Language to SQL experiment queries.

Translates natural language questions into SQL queries against the experiment
database, optionally fetches rich data from S3, and synthesizes a natural
language answer.
"""
from __future__ import annotations

import logging
import re

import sqlparse

logger = logging.getLogger(__name__)

_ALLOWED_TABLES = {"experiments", "models", "runs"}
_MAX_LIMIT = 50


def validate_sql(sql: str) -> tuple[str, str | None]:
    """Validate and sanitize a SQL query.

    Returns ``(validated_sql, None)`` on success, or ``("", error_message)`` on failure.
    """
    parsed = sqlparse.parse(sql)
    if len(parsed) != 1:
        return ("", "Query must be exactly one SQL statement.")

    stmt = parsed[0]

    # Must be SELECT
    if stmt.get_type() != "SELECT":
        return ("", "Solo se permiten consultas SELECT.")

    # Check tables — extract identifiers from the SQL
    # Use a simple regex approach: find words after FROM and JOIN keywords
    upper_sql = sql.upper()
    table_pattern = r'\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
    found_tables = {m.group(1).lower() for m in re.finditer(table_pattern, sql, re.IGNORECASE)}

    disallowed = found_tables - _ALLOWED_TABLES
    if disallowed:
        return ("", f"Tablas no permitidas: {', '.join(sorted(disallowed))}. Solo: {', '.join(sorted(_ALLOWED_TABLES))}.")

    # Enforce LIMIT
    validated = sql.rstrip().rstrip(";")

    # Check for existing LIMIT
    limit_match = re.search(r'\bLIMIT\s+(\d+)', validated, re.IGNORECASE)
    if limit_match:
        current_limit = int(limit_match.group(1))
        if current_limit > _MAX_LIMIT:
            validated = re.sub(
                r'\bLIMIT\s+\d+',
                f'LIMIT {_MAX_LIMIT}',
                validated,
                flags=re.IGNORECASE,
            )
    else:
        validated = f"{validated} LIMIT {_MAX_LIMIT}"

    return (validated, None)

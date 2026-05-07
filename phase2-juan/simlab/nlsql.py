"""NLSQL — Natural Language to SQL experiment queries.

Translates natural language questions into SQL queries against the experiment
database, optionally fetches rich data from S3, and synthesizes a natural
language answer.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime

import anthropic
import sqlparse
from sqlalchemy import text

import shared
from shared.settings import load_settings
from simlab.utils import strip_markdown_fences

logger = logging.getLogger(__name__)

_ALLOWED_TABLES = {"experiments", "models", "runs"}
_MAX_LIMIT = 50

_SCHEMA_PROMPT = """\
Tables available for querying:

experiments(id UUID PK, created_at TIMESTAMP, updated_at TIMESTAMP,
  description TEXT, status VARCHAR(50), spec JSONB, models_used JSONB,
  steps INT, seed INT, s3_events_key VARCHAR, s3_replay_key VARCHAR,
  s3_tracker_key VARCHAR, s3_analyst_key VARCHAR, s3_pdf_key VARCHAR,
  s3_tex_key VARCHAR, s3_charts_prefix VARCHAR)

  status lifecycle: created → simulated → tracked → analyzed → reported
  models_used: JSON array of model keys e.g. ["prospect-theory/cumulative-pt"]
  spec: JSON with grid_width, grid_height, actions, resources, effects

models(id UUID PK, class_name VARCHAR, paradigm VARCHAR NOT NULL,
  formulation VARCHAR NOT NULL, description TEXT, run_id UUID FK→runs,
  s3_model_key VARCHAR, registered_at TIMESTAMP, metadata JSONB)

  UNIQUE(run_id, paradigm, formulation)

runs(id UUID PK, created_at TIMESTAMP, problem_description TEXT NOT NULL,
  status VARCHAR(50), s3_report_key VARCHAR, s3_prefix VARCHAR NOT NULL,
  artifact_count INT)

Tables NOT queryable: memories, artifacts.
Only SELECT queries are allowed. Results are capped at LIMIT 50."""


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


async def _plan(question: str) -> dict | None:
    """Translate a natural language question into a SQL plan via LLM.

    Returns a dict with keys ``sql``, ``fetch_s3``, ``reasoning``, or None if
    JSON parsing fails.
    """
    settings = load_settings()
    client = anthropic.AsyncAnthropic()
    system = (
        _SCHEMA_PROMPT
        + "\n\n"
        "You translate natural language questions about experiments into SQL queries. "
        "Return ONLY valid JSON with keys: sql, fetch_s3, reasoning. "
        "fetch_s3 is a list of S3 content types to fetch: any of "
        "['analyst', 'events', 'tracker', 'replay']. "
        "Each maps to s3_<type>_key column. "
        "Use null or [] if no S3 data needed."
    )
    response = await client.messages.create(
        model=settings.NLSQL_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": question}],
        system=system,
    )
    raw = strip_markdown_fences(response.content[0].text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("_plan: failed to parse LLM response as JSON: %r", raw)
        return None


async def _execute(sql: str) -> list[dict] | None:
    """Run a validated SQL query in a read-only transaction.

    Returns a list of row dicts, or None on error.
    """
    try:
        async with shared.db.get_session() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            result = await session.execute(text(sql))
            rows = result.mappings().all()
            serialized: list[dict] = []
            for row in rows:
                row_dict: dict = {}
                for key, value in row.items():
                    if isinstance(value, (uuid.UUID, datetime)):
                        row_dict[key] = str(value)
                    else:
                        row_dict[key] = value
                serialized.append(row_dict)
            return serialized
    except Exception:
        logger.warning("_execute: query failed", exc_info=True)
        return None


async def _fetch_s3(
    rows: list[dict],
    fetch_types: list[str],
    max_rows: int,
) -> dict[str, str]:
    """Fetch S3 content for the first *max_rows* rows in parallel.

    Returns a dict mapping ``"{experiment_id}:{type}"`` to truncated content
    (max ~4000 chars). Failures are silently skipped.
    """
    if not fetch_types or not rows:
        return {}

    _TYPE_TO_COLUMN = {
        "analyst": "s3_analyst_key",
        "events": "s3_events_key",
        "tracker": "s3_tracker_key",
        "replay": "s3_replay_key",
    }

    async def _fetch_one(exp_id: str, ftype: str, key: str) -> tuple[str, str] | None:
        try:
            content = await shared.storage.get_text(key)
            truncated = content[:4000]
            return (f"{exp_id}:{ftype}", truncated)
        except Exception:
            logger.warning("_fetch_s3: failed to fetch key=%r type=%r", key, ftype)
            return None

    tasks = []
    for row in rows[:max_rows]:
        exp_id = row.get("id", "unknown")
        for ftype in fetch_types:
            col = _TYPE_TO_COLUMN.get(ftype)
            if col is None:
                continue
            key = row.get(col)
            if key:
                tasks.append(_fetch_one(str(exp_id), ftype, key))

    if not tasks:
        return {}

    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: dict[str, str] = {}
    for res in results:
        if isinstance(res, tuple):
            out[res[0]] = res[1]
    return out


async def _synthesize(
    question: str,
    rows: list[dict],
    s3_data: dict[str, str],
    capped: bool,
) -> str:
    """Produce a natural language answer from query results via a second LLM call."""
    settings = load_settings()
    client = anthropic.AsyncAnthropic()

    # Build a compact text table of results
    if rows:
        columns = list(rows[0].keys())
        header = " | ".join(columns)
        separator = "-" * len(header)
        table_lines = [header, separator]
        for row in rows:
            table_lines.append(" | ".join(str(row.get(c, "")) for c in columns))
        table_text = "\n".join(table_lines)
    else:
        table_text = "(sin resultados)"

    # Build S3 snippets section
    s3_section = ""
    if s3_data:
        snippets = []
        for label, content in s3_data.items():
            snippets.append(f"--- {label} ---\n{content}")
        s3_section = "\n\nDatos adicionales de S3:\n" + "\n\n".join(snippets)

    capped_note = "\n\n(Nota: los resultados están limitados a 50 filas.)" if capped else ""

    user_content = (
        f"Pregunta: {question}\n\n"
        f"Resultados de la consulta:\n{table_text}"
        f"{s3_section}"
        f"{capped_note}"
    )

    response = await client.messages.create(
        model=settings.NLSQL_MODEL,
        max_tokens=1024,
        system=(
            "You answer questions about simulation experiments using query results. "
            "Answer in Spanish. Be concise and cite specific data."
        ),
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text.strip()


async def query_experiments(question: str) -> str:
    """Translate a natural language question into SQL, execute it, and synthesize an answer.

    Never raises — all error paths return a user-friendly Spanish string.
    """
    settings = load_settings()

    # 1. Plan
    plan = await _plan(question)
    if plan is None:
        return "No pude interpretar la pregunta. Intenta reformularla."

    sql_raw = plan.get("sql", "")
    fetch_types: list[str] = plan.get("fetch_s3") or []

    # 2. Validate
    validated_sql, error = validate_sql(sql_raw)
    if error:
        return error

    # 3. Execute
    rows = await _execute(validated_sql)
    if rows is None:
        return "Error al ejecutar la consulta."

    if not rows:
        return "No encontré experimentos que coincidan con tu búsqueda."

    capped = len(rows) == _MAX_LIMIT

    # 4. Fetch S3
    s3_data = await _fetch_s3(rows, fetch_types, settings.NLSQL_MAX_S3_FETCH)

    # 5. Synthesize
    try:
        return await _synthesize(question, rows, s3_data, capped)
    except Exception:
        logger.warning("_synthesize failed; falling back to plain table", exc_info=True)
        if rows:
            columns = list(rows[0].keys())
            lines = [" | ".join(columns)]
            lines.append("-" * len(lines[0]))
            for row in rows:
                lines.append(" | ".join(str(row.get(c, "")) for c in columns))
            return "\n".join(lines)
        return "No encontré experimentos que coincidan con tu búsqueda."

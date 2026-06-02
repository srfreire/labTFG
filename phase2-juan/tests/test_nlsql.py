"""P1-004 — Unit and integration tests for the NLSQL module.

All external dependencies (LLM, Postgres, S3) are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from simlab.nlsql import validate_sql

# ---------------------------------------------------------------------------
# Validator tests — pure function, no mocks needed
# ---------------------------------------------------------------------------


def test_validate_select_only():
    """Rejects INSERT, UPDATE, DELETE, DROP."""
    for stmt in [
        "INSERT INTO experiments VALUES (1)",
        "UPDATE experiments SET status='done'",
        "DELETE FROM experiments",
        "DROP TABLE experiments",
    ]:
        sql, error = validate_sql(stmt)
        assert error is not None, f"Should reject: {stmt}"


def test_validate_allowed_tables():
    """Rejects queries on tables not in allowlist."""
    sql, error = validate_sql("SELECT * FROM artifacts")
    assert error is not None
    assert "artifacts" in error

    sql, error = validate_sql("SELECT * FROM pg_user LIMIT 10")
    assert error is not None
    assert "pg_user" in error


def test_validate_allowed_tables_pass():
    """Accepts queries on allowed tables."""
    sql, error = validate_sql("SELECT id FROM experiments")
    assert error is None

    sql, error = validate_sql(
        "SELECT paradigm, formulation FROM simulation_observations "
        "WHERE phase2_experiment_id = 'exp-1'"
    )
    assert error is None


def test_validate_chat_messages_passes():
    """P3-001: chat_messages is in the whitelist."""
    sql, error = validate_sql("SELECT * FROM chat_messages LIMIT 10")
    assert error is None


def test_validate_pipeline_memories_passes():
    """P3-001: pipeline_memories is in the whitelist."""
    sql, error = validate_sql("SELECT content FROM pipeline_memories LIMIT 10")
    assert error is None


def test_validate_join_chat_to_experiments():
    """P3-001: chat_messages ↔ experiments join works under the whitelist."""
    sql, error = validate_sql(
        "SELECT c.content FROM chat_messages c "
        "JOIN experiments e ON c.experiment_id = e.id LIMIT 5"
    )
    assert error is None


def test_validate_limit_enforced():
    """Adds LIMIT 50 if missing."""
    sql, error = validate_sql("SELECT id FROM experiments")
    assert error is None
    assert "LIMIT 50" in sql.upper()


def test_validate_limit_capped():
    """Rewrites LIMIT > 50 to LIMIT 50."""
    sql, error = validate_sql("SELECT id FROM experiments LIMIT 100")
    assert error is None
    assert "LIMIT 50" in sql


def test_validate_limit_preserved():
    """Keeps LIMIT <= 50 as-is."""
    sql, error = validate_sql("SELECT id FROM experiments LIMIT 10")
    assert error is None
    assert "LIMIT 10" in sql


def test_validate_valid_join():
    """Accepts JOIN between allowed tables."""
    sql, error = validate_sql(
        "SELECT e.id FROM experiments e JOIN models m ON e.id = m.id"
    )
    assert error is None


# ---------------------------------------------------------------------------
# Plan tests — mock LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_valid_json():
    """Mock LLM returns valid JSON plan."""
    from simlab.nlsql import _plan

    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text='{"sql": "SELECT id FROM experiments", "fetch_s3": ["analyst"], "reasoning": "need analyst data"}'
        )
    ]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("simlab.nlsql.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await _plan("what experiments have I run?")

    assert result is not None
    assert result["sql"] == "SELECT id FROM experiments"
    assert result["fetch_s3"] == ["analyst"]


@pytest.mark.asyncio
async def test_plan_invalid_json():
    """Mock LLM returns garbage — _plan returns None."""
    from simlab.nlsql import _plan

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="I cannot help with that")]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("simlab.nlsql.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await _plan("what experiments have I run?")

    assert result is None


# ---------------------------------------------------------------------------
# S3 fetch tests — pass an explicit StorageService mock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s3_fetch_respects_limit():
    """Only fetches up to max_rows."""
    from simlab.nlsql import _fetch_s3

    rows = [
        {"id": "exp1", "s3_analyst_key": "key1"},
        {"id": "exp2", "s3_analyst_key": "key2"},
        {"id": "exp3", "s3_analyst_key": "key3"},
        {"id": "exp4", "s3_analyst_key": "key4"},
    ]

    mock_storage = AsyncMock()
    mock_storage.get_text = AsyncMock(return_value='{"data": "test"}')

    await _fetch_s3(rows, ["analyst"], max_rows=2, storage=mock_storage)

    # Should only fetch 2 rows, not 4
    assert mock_storage.get_text.call_count == 2


@pytest.mark.asyncio
async def test_s3_fetch_partial_failure():
    """One fetch fails, others succeed."""
    from simlab.nlsql import _fetch_s3

    rows = [
        {"id": "exp1", "s3_analyst_key": "key1"},
        {"id": "exp2", "s3_analyst_key": "key2"},
    ]

    mock_storage = AsyncMock()
    mock_storage.get_text = AsyncMock(
        side_effect=['{"data": "ok"}', RuntimeError("S3 down")]
    )

    result = await _fetch_s3(rows, ["analyst"], max_rows=2, storage=mock_storage)

    # Should have 1 result (the successful one)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_s3_fetch_truncation():
    """Content > 4000 chars is truncated to 4000 chars."""
    from simlab.nlsql import _fetch_s3

    rows = [{"id": "exp1", "s3_analyst_key": "key1"}]
    long_content = "x" * 8000

    mock_storage = AsyncMock()
    mock_storage.get_text = AsyncMock(return_value=long_content)

    result = await _fetch_s3(rows, ["analyst"], max_rows=1, storage=mock_storage)

    for v in result.values():
        assert len(v) <= 4100  # 4000 + some truncation marker


# ---------------------------------------------------------------------------
# Integration roundtrip tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_experiments_roundtrip():
    """Full pipeline: question → plan → validate → execute → synthesize → answer."""
    from simlab.nlsql import query_experiments

    # Mock plan LLM
    plan_response = MagicMock()
    plan_response.content = [
        MagicMock(
            text='{"sql": "SELECT id, description FROM experiments", "fetch_s3": null, "reasoning": "list experiments"}'
        )
    ]

    # Mock synthesize LLM
    synth_response = MagicMock()
    synth_response.content = [MagicMock(text="Tienes 2 experimentos recientes.")]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=[plan_response, synth_response])

    # Mock Postgres — _execute calls session.execute twice:
    # once for SET TRANSACTION READ ONLY and once for the actual query
    set_tx_result = MagicMock()
    mock_row1 = {"id": "uuid-1", "description": "test exp 1"}
    mock_row2 = {"id": "uuid-2", "description": "test exp 2"}
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [mock_row1, mock_row2]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[set_tx_result, mock_result])
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_settings = MagicMock()
    mock_settings.NLSQL_MODEL = "claude-haiku"
    mock_settings.NLSQL_MAX_S3_FETCH = 3

    mock_db = MagicMock()
    mock_db.get_session = MagicMock(return_value=mock_session)
    mock_storage = AsyncMock()

    with (
        patch("simlab.nlsql.anthropic.AsyncAnthropic", return_value=mock_client),
        patch("simlab.nlsql.load_settings", return_value=mock_settings),
    ):
        answer = await query_experiments(
            "cuántos experimentos tengo?", db=mock_db, storage=mock_storage
        )

    assert "2 experimentos" in answer


@pytest.mark.asyncio
async def test_query_experiments_no_results():
    """Zero SQL results returns friendly message."""
    from simlab.nlsql import query_experiments

    plan_response = MagicMock()
    plan_response.content = [
        MagicMock(
            text='{"sql": "SELECT id FROM experiments WHERE description LIKE \'%nonexistent%\'", "fetch_s3": null, "reasoning": "search"}'
        )
    ]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=plan_response)

    set_tx_result = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[set_tx_result, mock_result])
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_settings = MagicMock()
    mock_settings.NLSQL_MODEL = "claude-haiku"
    mock_settings.NLSQL_MAX_S3_FETCH = 3

    mock_db = MagicMock()
    mock_db.get_session = MagicMock(return_value=mock_session)
    mock_storage = AsyncMock()

    with (
        patch("simlab.nlsql.anthropic.AsyncAnthropic", return_value=mock_client),
        patch("simlab.nlsql.load_settings", return_value=mock_settings),
    ):
        answer = await query_experiments(
            "find nonexistent experiments", db=mock_db, storage=mock_storage
        )

    assert "No encontré" in answer


@pytest.mark.asyncio
async def test_query_experiments_rejects_non_string_sql_plan():
    """Planner shape errors return a friendly rejection instead of raising."""
    from simlab.nlsql import query_experiments

    with (
        patch(
            "simlab.nlsql._plan",
            new=AsyncMock(
                return_value={
                    "sql": ["SELECT id FROM experiments"],
                    "fetch_s3": [],
                    "reasoning": "bad planner shape",
                }
            ),
        ),
        patch("simlab.nlsql._execute", new=AsyncMock()) as execute,
    ):
        answer = await query_experiments(
            "dame el experimento reciente",
            db=MagicMock(),
            storage=MagicMock(),
        )

    assert "Consulta rechazada" in answer
    assert "SQL debe ser texto" in answer
    execute.assert_not_called()

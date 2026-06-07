"""Variable's unique key is now `id` (composite paradigm_slug:name),
not the bare `name`."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.knowledge_graph import KnowledgeGraph


def test_variable_unique_key_is_id():
    assert KnowledgeGraph.unique_key_for("Variable") == "id"


def test_variable_indexes_include_paradigm_slug():
    info = KnowledgeGraph.SCHEMA["Variable"]
    assert "paradigm_slug" in info["indexes"]
    assert "name" in info["indexes"]


def test_parameter_unique_key_is_scoped_id():
    assert KnowledgeGraph.unique_key_for("Parameter") == "id"


def test_formulation_indexes_include_local_id_bridge():
    info = KnowledgeGraph.SCHEMA["Formulation"]
    assert "local_id" in info["indexes"]
    assert "paradigm_slug" in info["indexes"]


@pytest.mark.asyncio
async def test_init_schema_issues_run_ids_cleanup_cypher():
    """init_schema must REMOVE pre-P0-004 ``n.run_ids`` arrays idempotently.

    Mocks the Neo4j driver and asserts the cleanup query is among the
    Cypher statements issued during init_schema.  See migration
    ``d5f8a92b1c4e`` and MEMORY_SYSTEM_REPORT §6.4 for context.
    """
    cleanup_record = {"cleaned": 0}

    single_result = AsyncMock()
    single_result.single = AsyncMock(return_value=cleanup_record)

    mock_session = AsyncMock()
    mock_session.run.return_value = single_result

    @asynccontextmanager
    async def _session_cm():
        yield mock_session

    with patch("shared.knowledge_graph.AsyncGraphDatabase") as mock_agd:
        mock_driver = MagicMock()
        mock_driver.session = _session_cm
        mock_agd.driver.return_value = mock_driver
        kg = KnowledgeGraph("bolt://fake:7687", "neo4j", "test")

    await kg.init_schema()

    cypher_calls = [call.args[0] for call in mock_session.run.call_args_list]
    assert any("REMOVE n.run_ids" in c for c in cypher_calls), (
        f"init_schema must issue a REMOVE n.run_ids cleanup; got: {cypher_calls}"
    )

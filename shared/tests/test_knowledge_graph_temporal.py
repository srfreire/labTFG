"""Tests for KnowledgeGraph temporal query methods.

Per P4-004 ``query_at_time`` is a two-step helper: it first runs a PG
SELECT against ``pipeline_memories`` to get the live memory_ids at
*as_of*, then constrains the Neo4j MATCH with ``r.memory_id IN
$_valid_ids``.  These unit tests stub both the Neo4j driver and the
``select_valid_memory_ids`` helper so no real services are required.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared import knowledge_graph as kg_mod
from shared.knowledge_graph import KnowledgeGraph

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_kg_with_session(records: list[dict]) -> tuple[KnowledgeGraph, AsyncMock]:
    """Create a KnowledgeGraph with a mocked driver returning *records*."""
    mock_result = AsyncMock()

    async def _aiter(_self):
        for r in records:
            yield r

    mock_result.__aiter__ = _aiter

    mock_session = AsyncMock()
    mock_session.run.return_value = mock_result

    @asynccontextmanager
    async def _session_cm():
        yield mock_session

    with patch("shared.knowledge_graph.AsyncGraphDatabase") as mock_agd:
        mock_driver = MagicMock()
        mock_driver.session = _session_cm
        mock_agd.driver.return_value = mock_driver
        kg = KnowledgeGraph("bolt://fake:7687", "neo4j", "test")

    return kg, mock_session


def _stub_valid_ids(monkeypatch, ids: list[str]) -> AsyncMock:
    """Patch ``select_valid_memory_ids`` to return *ids*; return the mock."""
    spy = AsyncMock(return_value=ids)
    monkeypatch.setattr(kg_mod, "select_valid_memory_ids", spy)
    return spy


# ---------------------------------------------------------------------------
# query_at_time: two-step PG → Neo4j
# ---------------------------------------------------------------------------


class TestQueryAtTime:
    @pytest.mark.asyncio
    async def test_two_step_calls_pg_then_neo4j(self, monkeypatch):
        """First a PG SELECT for valid ids, then the Neo4j MATCH."""
        as_of = datetime(2026, 4, 10, tzinfo=UTC)
        valid_ids = ["mem-1", "mem-2"]
        spy = _stub_valid_ids(monkeypatch, valid_ids)

        kg, mock_session = _make_kg_with_session([{"name": "ghrelin"}])
        pg_session = MagicMock()

        result = await kg.query_at_time(
            "MATCH (n:Variable)-[r]->(m) RETURN n, r",
            as_of=as_of,
            session=pg_session,
        )

        assert len(result) == 1
        spy.assert_awaited_once()
        pg_arg, as_of_arg = spy.await_args.args[:2]
        assert pg_arg is pg_session
        assert as_of_arg == as_of

        cypher_sent = mock_session.run.call_args[0][0]
        assert "$_valid_ids" in cypher_sent
        assert "r.memory_id" in cypher_sent

    @pytest.mark.asyncio
    async def test_temporal_filter_inserted_before_return(self, monkeypatch):
        """The injected WHERE precedes RETURN, not the other way around."""
        _stub_valid_ids(monkeypatch, ["mem-1"])
        as_of = datetime(2026, 4, 10, tzinfo=UTC)
        kg, mock_session = _make_kg_with_session([])

        await kg.query_at_time(
            "MATCH (n:Variable)-[r]->(m) RETURN n, r",
            as_of=as_of,
            session=MagicMock(),
        )

        cypher_sent = mock_session.run.call_args[0][0]
        where_idx = cypher_sent.find("WHERE r.memory_id")
        return_idx = cypher_sent.upper().rfind("RETURN")
        assert where_idx != -1, "temporal WHERE not found"
        assert return_idx != -1, "RETURN not found"
        assert where_idx < return_idx

    @pytest.mark.asyncio
    async def test_passes_valid_ids_param(self, monkeypatch):
        """The PG-fetched id list is passed to Neo4j as ``$_valid_ids``."""
        valid_ids = ["a", "b", "c"]
        _stub_valid_ids(monkeypatch, valid_ids)
        as_of = datetime(2026, 4, 10, tzinfo=UTC)
        kg, mock_session = _make_kg_with_session([])

        await kg.query_at_time(
            "MATCH (n)-[r]->(m) RETURN n",
            as_of=as_of,
            session=MagicMock(),
        )

        params = mock_session.run.call_args[0][1]
        assert params["_valid_ids"] == valid_ids
        assert params["_as_of"] == as_of.isoformat()

    @pytest.mark.asyncio
    async def test_merges_user_params(self, monkeypatch):
        """User params merge with the injected ``_valid_ids`` / ``_as_of``."""
        _stub_valid_ids(monkeypatch, ["mem-1"])
        as_of = datetime(2026, 4, 10, tzinfo=UTC)
        kg, mock_session = _make_kg_with_session([])

        await kg.query_at_time(
            "MATCH (n:Variable {name: $name})-[r]->(m) RETURN n",
            as_of=as_of,
            session=MagicMock(),
            params={"name": "ghrelin"},
        )

        params = mock_session.run.call_args[0][1]
        assert params["name"] == "ghrelin"
        assert "_valid_ids" in params
        assert "_as_of" in params

    @pytest.mark.asyncio
    async def test_seed_relations_pass_through(self, monkeypatch):
        """Pre-P4-004 relations with no ``memory_id`` are always considered valid.

        The injected clause is ``r.memory_id IS NULL OR r.memory_id IN $_valid_ids``,
        which is the only way canonical seed relations stay visible.
        """
        _stub_valid_ids(monkeypatch, [])
        kg, mock_session = _make_kg_with_session([])

        await kg.query_at_time(
            "MATCH ()-[r]->() RETURN r",
            as_of=datetime(2026, 4, 10, tzinfo=UTC),
            session=MagicMock(),
        )

        cypher_sent = mock_session.run.call_args[0][0]
        assert "r.memory_id IS NULL" in cypher_sent

    @pytest.mark.asyncio
    async def test_returns_deserialized_dicts(self, monkeypatch):
        _stub_valid_ids(monkeypatch, ["mem-1"])
        kg, _ = _make_kg_with_session([{"name": "ghrelin", "score": 0.9}])

        result = await kg.query_at_time(
            "MATCH (n)-[r]->(m) RETURN n.name AS name",
            as_of=datetime(2026, 4, 10, tzinfo=UTC),
            session=MagicMock(),
        )

        assert isinstance(result, list)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# get_node_history: now joins through PG for temporal metadata
# ---------------------------------------------------------------------------


class TestGetNodeHistory:
    @pytest.mark.asyncio
    async def test_joins_pg_temporal_metadata(self, monkeypatch):
        """Returned rows carry valid_from/valid_to/confidence from PG."""
        records = [
            {
                "type": "MODULATES",
                "props": {"memory_id": "mem-1"},
                "neighbor": {"name": "energy_level"},
                "memory_id": "mem-1",
            },
            {
                "type": "MODULATES",
                "props": {"memory_id": "mem-2"},
                "neighbor": {"name": "energy_level"},
                "memory_id": "mem-2",
            },
        ]
        kg, _ = _make_kg_with_session(records)

        async def _fake_meta(_session, ids, *, namespace):
            return {
                "mem-1": {
                    "valid_from": "2026-04-01T00:00:00",
                    "valid_to": "2026-04-05T00:00:00",
                    "confidence": 0.8,
                },
                "mem-2": {
                    "valid_from": "2026-04-05T00:00:00",
                    "valid_to": None,
                    "confidence": 0.9,
                },
            }

        monkeypatch.setattr(kg_mod, "fetch_memory_temporal_meta", _fake_meta)

        result = await kg.get_node_history(
            "Variable", "name", "ghrelin", session=MagicMock()
        )

        assert len(result) == 2
        # Sorted by valid_from ASC.
        assert result[0]["valid_from"] == "2026-04-01T00:00:00"
        assert result[0]["confidence"] == 0.8
        assert result[1]["valid_to"] is None

    @pytest.mark.asyncio
    async def test_seed_relations_have_null_temporal_fields(self, monkeypatch):
        """Relations without memory_id stay in the result with None fields."""
        records = [
            {
                "type": "BELONGS_TO",
                "props": {},
                "neighbor": {"slug": "homeostatic"},
                "memory_id": None,
            },
        ]
        kg, _ = _make_kg_with_session(records)

        async def _fake_meta(*_a, **_kw):
            return {}

        monkeypatch.setattr(kg_mod, "fetch_memory_temporal_meta", _fake_meta)

        result = await kg.get_node_history(
            "Variable", "name", "x", session=MagicMock()
        )

        assert len(result) == 1
        assert result[0]["valid_from"] is None
        assert result[0]["valid_to"] is None
        assert result[0]["confidence"] is None

    @pytest.mark.asyncio
    async def test_validates_label(self):
        kg, _ = _make_kg_with_session([])
        with pytest.raises(ValueError, match="Unknown label"):
            await kg.get_node_history(
                "FakeLabel", "name", "test", session=MagicMock()
            )

    @pytest.mark.asyncio
    async def test_validates_key_property(self):
        kg, _ = _make_kg_with_session([])
        with pytest.raises(ValueError, match="Invalid"):
            await kg.get_node_history(
                "Variable", "bad prop!", "test", session=MagicMock()
            )

    @pytest.mark.asyncio
    async def test_empty_history(self):
        kg, _ = _make_kg_with_session([])
        result = await kg.get_node_history(
            "Variable", "name", "unknown", session=MagicMock()
        )
        assert result == []

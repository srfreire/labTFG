"""Tests for KnowledgeGraph temporal query methods (P5-004).

Unit tests using a mock Neo4j driver — no real DB required.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.knowledge_graph import KnowledgeGraph

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_kg_with_session(records: list[dict]) -> tuple[KnowledgeGraph, AsyncMock]:
    """Create a KnowledgeGraph with a mocked driver returning *records*.

    Returns (kg, mock_session) so tests can inspect run() call args.
    """
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


# ---------------------------------------------------------------------------
# AC2: query_at_time filters by temporal validity
# ---------------------------------------------------------------------------


class TestQueryAtTime:
    @pytest.mark.asyncio
    async def test_wraps_cypher_with_temporal_filter(self):
        """query_at_time adds valid_from/valid_to filtering to relations."""
        as_of = datetime(2026, 4, 10, tzinfo=UTC)
        kg, mock_session = _make_kg_with_session([{"name": "ghrelin"}])

        result = await kg.query_at_time(
            "MATCH (n:Variable)-[r]->(m) RETURN n, r",
            as_of=as_of,
        )

        assert len(result) == 1
        cypher_sent = mock_session.run.call_args[0][0]
        assert "valid_from" in cypher_sent
        assert "valid_to" in cypher_sent
        assert "$_as_of" in cypher_sent

    @pytest.mark.asyncio
    async def test_temporal_filter_inserted_before_return(self):
        """The WHERE filter appears before the RETURN clause, not after."""
        as_of = datetime(2026, 4, 10, tzinfo=UTC)
        kg, mock_session = _make_kg_with_session([])

        await kg.query_at_time(
            "MATCH (n:Variable)-[r]->(m) RETURN n, r",
            as_of=as_of,
        )

        cypher_sent = mock_session.run.call_args[0][0]
        where_idx = cypher_sent.find("WHERE r.valid_from")
        return_idx = cypher_sent.upper().rfind("RETURN")
        assert where_idx != -1, "temporal WHERE not found"
        assert return_idx != -1, "RETURN not found"
        assert where_idx < return_idx, (
            f"WHERE ({where_idx}) must appear before RETURN ({return_idx})"
        )

    @pytest.mark.asyncio
    async def test_passes_as_of_param(self):
        """query_at_time passes as_of as a parameter to Neo4j."""
        as_of = datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC)
        kg, mock_session = _make_kg_with_session([])

        await kg.query_at_time("MATCH (n)-[r]->(m) RETURN n", as_of=as_of)

        params = mock_session.run.call_args[0][1]
        assert params["_as_of"] == as_of.isoformat()

    @pytest.mark.asyncio
    async def test_merges_user_params(self):
        """query_at_time merges user params with _as_of."""
        as_of = datetime(2026, 4, 10, tzinfo=UTC)
        kg, mock_session = _make_kg_with_session([])

        await kg.query_at_time(
            "MATCH (n:Variable {name: $name})-[r]->(m) RETURN n",
            as_of=as_of,
            params={"name": "ghrelin"},
        )

        params = mock_session.run.call_args[0][1]
        assert params["name"] == "ghrelin"
        assert "_as_of" in params

    @pytest.mark.asyncio
    async def test_returns_deserialized_dicts(self):
        """query_at_time returns list of dicts, same as query()."""
        as_of = datetime(2026, 4, 10, tzinfo=UTC)
        kg, _ = _make_kg_with_session([{"name": "ghrelin", "score": 0.9}])

        result = await kg.query_at_time(
            "MATCH (n)-[r]->(m) RETURN n.name AS name",
            as_of=as_of,
        )

        assert isinstance(result, list)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# get_node_history: returns all versions of a node's relations
# ---------------------------------------------------------------------------


class TestGetNodeHistory:
    @pytest.mark.asyncio
    async def test_returns_relations_ordered_by_valid_from(self):
        """get_node_history returns relation dicts with type, props, neighbor."""
        records = [
            {
                "type": "MODULATES",
                "props": {
                    "confidence": 0.8,
                    "valid_from": "2026-04-01T00:00:00Z",
                    "valid_to": "2026-04-05T00:00:00Z",
                },
                "neighbor": {"name": "energy_level"},
            },
            {
                "type": "MODULATES",
                "props": {
                    "confidence": 0.9,
                    "valid_from": "2026-04-05T00:00:00Z",
                    "valid_to": None,
                },
                "neighbor": {"name": "energy_level"},
            },
        ]
        kg, mock_session = _make_kg_with_session(records)

        result = await kg.get_node_history("Variable", "name", "ghrelin")

        assert len(result) == 2
        cypher_sent = mock_session.run.call_args[0][0]
        assert "Variable" in cypher_sent
        assert "ORDER BY" in cypher_sent

    @pytest.mark.asyncio
    async def test_validates_label(self):
        """get_node_history raises ValueError for unknown labels."""
        kg, _ = _make_kg_with_session([])
        with pytest.raises(ValueError, match="Unknown label"):
            await kg.get_node_history("FakeLabel", "name", "test")

    @pytest.mark.asyncio
    async def test_validates_key_property(self):
        """get_node_history raises ValueError for invalid key property."""
        kg, _ = _make_kg_with_session([])
        with pytest.raises(ValueError, match="Invalid"):
            await kg.get_node_history("Variable", "bad prop!", "test")

    @pytest.mark.asyncio
    async def test_empty_history(self):
        """get_node_history returns empty list when node has no relations."""
        kg, _ = _make_kg_with_session([])
        result = await kg.get_node_history("Variable", "name", "unknown")
        assert result == []

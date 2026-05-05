"""Tests for ``decisionlab.eval.kgadmin``.

The KG itself is mocked — we exercise:
- ``stats`` aggregation logic over fake Cypher row dicts
- ``reset`` confirmation guard + node-count return
- ``snapshot`` round-trip serializability
- ``query`` pass-through
- ``_require_kg`` raises when shared.kg is None
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from decisionlab.eval import kgadmin


def _fake_kg(query_responses: dict[str, list[dict]]) -> AsyncMock:
    """Build a fake KG whose ``query()`` returns rows based on a substring
    match against the cypher string. First match wins."""

    async def _q(cypher: str, params: dict | None = None):
        for needle, rows in query_responses.items():
            if needle in cypher:
                return rows
        return []

    kg = AsyncMock()
    kg.query = AsyncMock(side_effect=_q)
    return kg


# ---------------------------------------------------------------------------
# _require_kg
# ---------------------------------------------------------------------------


class TestRequireKG:
    def test_raises_when_kg_none(self):
        with patch("shared.kg", None, create=True):
            with pytest.raises(RuntimeError, match="not initialised"):
                kgadmin._require_kg()

    def test_returns_when_kg_set(self):
        sentinel = object()
        with patch("shared.kg", sentinel, create=True):
            assert kgadmin._require_kg() is sentinel


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


class TestStats:
    @pytest.mark.asyncio
    async def test_aggregates_counts_and_buckets(self):
        kg = _fake_kg(
            {
                "RETURN count(n)": [{"n": 42}],
                "RETURN count(r)": [{"n": 17}],
                "UNWIND labels(n)": [
                    {"label": "Paradigm", "n": 10},
                    {"label": "Variable", "n": 32},
                ],
                "type(r)": [
                    {"rel_type": "BELONGS_TO", "n": 12},
                    {"rel_type": "DEPENDS_ON", "n": 5},
                ],
            }
        )
        with patch("shared.kg", kg, create=True):
            result = await kgadmin.stats()

        assert result.total_nodes == 42
        assert result.total_relations == 17
        assert result.by_label == {"Paradigm": 10, "Variable": 32}
        assert result.by_type == {"BELONGS_TO": 12, "DEPENDS_ON": 5}
        # Round-trip through to_dict.
        d = result.to_dict()
        assert d["total_nodes"] == 42
        assert "BELONGS_TO" in d["by_type"]

    @pytest.mark.asyncio
    async def test_empty_graph_returns_zeros(self):
        kg = _fake_kg(
            {
                "RETURN count(n)": [{"n": 0}],
                "RETURN count(r)": [{"n": 0}],
                "UNWIND labels(n)": [],
                "type(r)": [],
            }
        )
        with patch("shared.kg", kg, create=True):
            result = await kgadmin.stats()
        assert result.total_nodes == 0
        assert result.total_relations == 0
        assert result.by_label == {}
        assert result.by_type == {}


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


class TestReset:
    @pytest.mark.asyncio
    async def test_requires_confirm(self):
        kg = _fake_kg({})
        with patch("shared.kg", kg, create=True):
            with pytest.raises(RuntimeError, match="confirm=True"):
                await kgadmin.reset()
        kg.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_node_count_and_runs_delete(self):
        kg = _fake_kg(
            {
                "count(n)": [{"n": 9}],
                "DETACH DELETE": [],
            }
        )
        with patch("shared.kg", kg, create=True):
            n = await kgadmin.reset(confirm=True)
        assert n == 9
        # Verify both queries (count + delete) ran.
        cyphers = [c.args[0] for c in kg.query.call_args_list]
        assert any("DETACH DELETE" in c for c in cyphers)


# ---------------------------------------------------------------------------
# snapshot / restore
# ---------------------------------------------------------------------------


class TestSnapshot:
    @pytest.mark.asyncio
    async def test_returns_serializable_payload(self):
        kg = _fake_kg(
            {
                "properties(n)": [
                    {"id": "n0", "labels": ["Paradigm"], "props": {"slug": "rl"}},
                ],
                "type(r)": [
                    {
                        "id": "r0",
                        "source": "n0",
                        "target": "n0",
                        "type": "BELONGS_TO",
                        "props": {"valid_from": "2026-01-01"},
                    }
                ],
            }
        )
        with patch("shared.kg", kg, create=True):
            snap = await kgadmin.snapshot()

        # Must be JSON-roundtrippable.
        assert json.loads(json.dumps(snap, default=str))
        assert snap["nodes"][0]["id"] == "n0"
        assert snap["relations"][0]["type"] == "BELONGS_TO"

    @pytest.mark.asyncio
    async def test_snapshot_to_file(self, tmp_path):
        kg = _fake_kg(
            {
                "properties(n)": [
                    {"id": "n0", "labels": ["Paradigm"], "props": {"slug": "rl"}}
                ],
                "type(r)": [],
            }
        )
        with patch("shared.kg", kg, create=True):
            await kgadmin.snapshot_to_file(tmp_path / "snap.json")
        data = json.loads((tmp_path / "snap.json").read_text())
        assert data["nodes"][0]["props"]["slug"] == "rl"


class TestRestore:
    @pytest.mark.asyncio
    async def test_resets_then_recreates(self):
        # Track the order of cypher calls.
        order: list[str] = []

        async def _q(cypher: str, params: dict | None = None):
            order.append(cypher)
            if "RETURN id(n)" in cypher:
                return [{"new_id": 99}]
            if "count(n)" in cypher:
                return [{"n": 0}]
            return []

        kg = AsyncMock()
        kg.query = AsyncMock(side_effect=_q)
        snap = {
            "nodes": [
                {"id": "old-n0", "labels": ["Paradigm"], "props": {"slug": "rl"}}
            ],
            "relations": [],
        }
        with patch("shared.kg", kg, create=True):
            await kgadmin.restore(snap)

        # First call after reset must be DETACH DELETE.
        assert any("DETACH DELETE" in c for c in order)
        # And we must have CREATE'd a node afterwards.
        assert any("CREATE (n:Paradigm)" in c for c in order)


# ---------------------------------------------------------------------------
# raw query pass-through
# ---------------------------------------------------------------------------


class TestQuery:
    @pytest.mark.asyncio
    async def test_passes_cypher_and_params(self):
        kg = AsyncMock()
        kg.query = AsyncMock(return_value=[{"x": 1}])
        with patch("shared.kg", kg, create=True):
            rows = await kgadmin.query(
                "MATCH (n) WHERE n.slug = $s RETURN n", {"s": "rl"}
            )
        assert rows == [{"x": 1}]
        kg.query.assert_awaited_once_with(
            "MATCH (n) WHERE n.slug = $s RETURN n", {"s": "rl"}
        )

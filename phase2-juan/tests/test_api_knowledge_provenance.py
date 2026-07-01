"""Tests for /api/knowledge/provenance/{node_id} endpoint (knowledge P7-003)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import simlab.api as api_module
from fastapi import HTTPException
from simlab.api import knowledge_provenance


def _row(
    *,
    node: dict | None,
    edges: list[dict] | None = None,
    nodes: list[dict] | None = None,
) -> dict:
    """Shape the fused Cypher returns: one row with node fields + best path."""
    if node is None:
        return {}
    edge_lists: list[list[dict]] = [edges] if edges is not None else []
    node_lists: list[list[dict]] = [nodes] if nodes is not None else []
    return {
        "id": node["id"],
        "labels": node["labels"],
        "props": node["props"],
        "edge_lists": edge_lists,
        "node_lists": node_lists,
    }


def _stub_kg(*, rows: list[dict]) -> MagicMock:
    """Fake Neo4j client whose single ``query`` returns ``rows`` verbatim."""
    kg = MagicMock()
    kg.captured_queries: list[str] = []

    async def query(cypher: str, params: dict | None = None) -> list[dict]:
        kg.captured_queries.append(cypher)
        return rows

    kg.query = query
    return kg


def _set_services(monkeypatch, *, kg=None):
    services = MagicMock()
    services.kg = kg
    monkeypatch.setattr(api_module, "_services", services)


async def test_returns_trail_for_postulate_supported_by_paper(monkeypatch):
    row = _row(
        node={"id": "n1", "labels": ["Postulate"], "props": {"name": "P1"}},
        edges=[{"id": "e1", "type": "SUPPORTED_BY", "props": {"weight": 0.9}}],
        nodes=[{"id": "p1", "labels": ["Paper"], "props": {"title": "X"}}],
    )
    _set_services(monkeypatch, kg=_stub_kg(rows=[row]))

    body = await knowledge_provenance(node_id="n1")

    assert body["node"]["id"] == "n1"
    assert body["node"]["label"] == "Postulate"
    assert len(body["trail"]) == 1
    step = body["trail"][0]
    assert step["edge"]["type"] == "SUPPORTED_BY"
    assert step["edge"]["props"] == {"weight": 0.9}
    assert step["node"]["label"] == "Paper"
    assert step["node"]["props"] == {"title": "X"}


async def test_empty_trail_when_no_path_to_paper(monkeypatch):
    row = _row(node={"id": "orphan", "labels": ["Postulate"], "props": {"name": "P9"}})
    _set_services(monkeypatch, kg=_stub_kg(rows=[row]))

    body = await knowledge_provenance(node_id="orphan")

    assert body["node"]["id"] == "orphan"
    assert body["trail"] == []


async def test_returns_404_when_node_missing(monkeypatch):
    _set_services(monkeypatch, kg=_stub_kg(rows=[]))

    with pytest.raises(HTTPException) as exc:
        await knowledge_provenance(node_id="ghost")

    assert exc.value.status_code == 404


async def test_path_cypher_caps_depth_and_fanout(monkeypatch):
    kg = _stub_kg(rows=[])
    _set_services(monkeypatch, kg=kg)

    with pytest.raises(HTTPException):
        await knowledge_provenance(node_id="n1")

    cypher = kg.captured_queries[0]
    assert "[*1..4]" in cypher
    assert "LIMIT 25" in cypher


async def test_returns_503_when_kg_is_none(monkeypatch):
    _set_services(monkeypatch, kg=None)

    with pytest.raises(HTTPException) as exc:
        await knowledge_provenance(node_id="n1")

    assert exc.value.status_code == 503


async def test_returns_503_when_services_is_none(monkeypatch):
    monkeypatch.setattr(api_module, "_services", None)

    with pytest.raises(HTTPException) as exc:
        await knowledge_provenance(node_id="n1")

    assert exc.value.status_code == 503


async def test_returns_503_when_query_raises(monkeypatch):
    kg = MagicMock()

    async def boom(_cypher: str, params: dict | None = None) -> list[dict]:
        raise RuntimeError("Neo4j connection lost")

    kg.query = boom
    _set_services(monkeypatch, kg=kg)

    with pytest.raises(HTTPException) as exc:
        await knowledge_provenance(node_id="n1")

    assert exc.value.status_code == 503


async def test_picks_longest_path_from_server_order(monkeypatch):
    """Cypher ORDER BY length DESC + LIMIT 1 means the route just reads the
    only path the server sends back."""
    row = _row(
        node={"id": "n1", "labels": ["Postulate"], "props": {}},
        edges=[
            {"id": "e1", "type": "DERIVES_FROM", "props": {}},
            {"id": "e2", "type": "AUTHORED", "props": {}},
            {"id": "e3", "type": "CITES", "props": {}},
        ],
        nodes=[
            {"id": "n2", "labels": ["Theory"], "props": {}},
            {"id": "n3", "labels": ["Author"], "props": {}},
            {"id": "p1", "labels": ["Paper"], "props": {}},
        ],
    )
    _set_services(monkeypatch, kg=_stub_kg(rows=[row]))

    body = await knowledge_provenance(node_id="n1")

    assert [s["edge"]["type"] for s in body["trail"]] == [
        "DERIVES_FROM",
        "AUTHORED",
        "CITES",
    ]

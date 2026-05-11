"""Tests for /api/knowledge/provenance/{node_id} endpoint (knowledge P7-003)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import simlab.api as api_module
from fastapi import HTTPException
from simlab.api import knowledge_provenance


def _stub_kg(*, node: dict | None, paths: list[dict]) -> MagicMock:
    """Build a fake Neo4j client.

    First ``query`` call (node lookup) returns ``[node]`` or ``[]``.
    Subsequent calls (path walk) return ``paths``.
    """
    kg = MagicMock()
    kg.captured_queries: list[str] = []

    async def query(cypher: str, params: dict | None = None) -> list[dict]:
        kg.captured_queries.append(cypher)
        if "MATCH (n) WHERE elementId(n)" in cypher and "path" not in cypher:
            return [node] if node is not None else []
        return paths

    kg.query = query
    return kg


def _set_services(monkeypatch, *, kg=None):
    services = MagicMock()
    services.kg = kg
    monkeypatch.setattr(api_module, "_services", services)


# ---------------------------------------------------------------------------
# AC1 — trail returned for a node with a path to a Paper
# ---------------------------------------------------------------------------


async def test_returns_trail_for_postulate_supported_by_paper(monkeypatch):
    node = {"id": "n1", "labels": ["Postulate"], "props": {"name": "P1"}}
    paths = [
        {
            "edges": [
                {"id": "e1", "type": "SUPPORTED_BY", "props": {"weight": 0.9}},
            ],
            "path_nodes": [
                {"id": "p1", "labels": ["Paper"], "props": {"title": "X"}},
            ],
        }
    ]
    _set_services(monkeypatch, kg=_stub_kg(node=node, paths=paths))

    body = await knowledge_provenance(node_id="n1")

    assert body["node"]["id"] == "n1"
    assert body["node"]["label"] == "Postulate"
    assert len(body["trail"]) == 1
    step = body["trail"][0]
    assert step["edge"]["type"] == "SUPPORTED_BY"
    assert step["edge"]["props"] == {"weight": 0.9}
    assert step["node"]["label"] == "Paper"
    assert step["node"]["props"] == {"title": "X"}


# ---------------------------------------------------------------------------
# AC2 — empty trail when node exists but has no path to a Paper
# ---------------------------------------------------------------------------


async def test_empty_trail_when_no_path_to_paper(monkeypatch):
    node = {"id": "orphan", "labels": ["Postulate"], "props": {"name": "P9"}}
    _set_services(monkeypatch, kg=_stub_kg(node=node, paths=[]))

    body = await knowledge_provenance(node_id="orphan")

    assert body["node"]["id"] == "orphan"
    assert body["trail"] == []


# ---------------------------------------------------------------------------
# AC3 — 404 when node does not exist
# ---------------------------------------------------------------------------


async def test_returns_404_when_node_missing(monkeypatch):
    _set_services(monkeypatch, kg=_stub_kg(node=None, paths=[]))

    with pytest.raises(HTTPException) as exc:
        await knowledge_provenance(node_id="ghost")

    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# AC4 — depth bound of 4 is enforced (verified by Cypher inspection)
# ---------------------------------------------------------------------------


async def test_path_cypher_caps_depth_at_four(monkeypatch):
    node = {"id": "n1", "labels": ["Postulate"], "props": {}}
    kg = _stub_kg(node=node, paths=[])
    _set_services(monkeypatch, kg=kg)

    await knowledge_provenance(node_id="n1")

    path_cyphers = [q for q in kg.captured_queries if "MATCH path" in q]
    assert path_cyphers, "expected at least one path query"
    assert "[*1..4]" in path_cyphers[0]
    # LIMIT clause caps fan-out
    assert "LIMIT 25" in path_cyphers[0]


# ---------------------------------------------------------------------------
# AC5 — 503 when Neo4j unavailable or query raises
# ---------------------------------------------------------------------------


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


async def test_returns_503_when_node_lookup_raises(monkeypatch):
    kg = MagicMock()

    async def boom(_cypher: str, params: dict | None = None) -> list[dict]:
        raise RuntimeError("Neo4j connection lost")

    kg.query = boom
    _set_services(monkeypatch, kg=kg)

    with pytest.raises(HTTPException) as exc:
        await knowledge_provenance(node_id="n1")

    assert exc.value.status_code == 503


async def test_returns_503_when_path_query_raises(monkeypatch):
    node = {"id": "n1", "labels": ["Postulate"], "props": {}}
    kg = MagicMock()
    calls = {"n": 0}

    async def maybe_boom(_cypher: str, params: dict | None = None) -> list[dict]:
        calls["n"] += 1
        if calls["n"] == 1:
            return [node]
        raise RuntimeError("path query down")

    kg.query = maybe_boom
    _set_services(monkeypatch, kg=kg)

    with pytest.raises(HTTPException) as exc:
        await knowledge_provenance(node_id="n1")

    assert exc.value.status_code == 503


# ---------------------------------------------------------------------------
# Extra — when multiple paths exist, pick the longest (most informative)
# ---------------------------------------------------------------------------


async def test_picks_longest_path_when_multiple(monkeypatch):
    node = {"id": "n1", "labels": ["Postulate"], "props": {}}
    paths = [
        {
            "edges": [
                {"id": "e1", "type": "DERIVES_FROM", "props": {}},
                {"id": "e2", "type": "AUTHORED", "props": {}},
                {"id": "e3", "type": "CITES", "props": {}},
            ],
            "path_nodes": [
                {"id": "n2", "labels": ["Theory"], "props": {}},
                {"id": "n3", "labels": ["Author"], "props": {}},
                {"id": "p1", "labels": ["Paper"], "props": {}},
            ],
        },
        {
            "edges": [{"id": "ex", "type": "SUPPORTED_BY", "props": {}}],
            "path_nodes": [{"id": "p2", "labels": ["Paper"], "props": {}}],
        },
    ]
    _set_services(monkeypatch, kg=_stub_kg(node=node, paths=paths))

    body = await knowledge_provenance(node_id="n1")

    assert len(body["trail"]) == 3
    assert [s["edge"]["type"] for s in body["trail"]] == [
        "DERIVES_FROM",
        "AUTHORED",
        "CITES",
    ]

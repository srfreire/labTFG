"""Tests for the /api/knowledge/graph endpoint (knowledge P7-001)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import simlab.api as api_module
from fastapi import HTTPException
from simlab.api import knowledge_graph


def _stub_kg(nodes: list[dict], edges: list[dict]) -> MagicMock:
    """Build a fake Neo4j client whose ``query`` returns canned nodes/edges."""
    kg = MagicMock()

    async def query(cypher: str) -> list[dict]:
        if "MATCH (n) RETURN elementId" in cypher:
            return nodes
        return edges

    kg.query = query
    return kg


def _stub_db_with_observations(rows: list[tuple[str, str]]) -> MagicMock:
    """Build a fake DatabaseService whose session returns the given rows."""
    session = MagicMock()
    result_obj = MagicMock()
    row_objs = [MagicMock(label=label, key_value=key) for label, key in rows]
    result_obj.all = MagicMock(return_value=row_objs)
    session.execute = AsyncMock(return_value=result_obj)

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)

    db = MagicMock()
    db.get_session = MagicMock(return_value=cm)
    return db


def _set_services(monkeypatch, *, kg=None, db=None):
    services = MagicMock()
    services.kg = kg
    services.db = db
    monkeypatch.setattr(api_module, "_services", services)


# ---------------------------------------------------------------------------
# AC1 — happy path
# ---------------------------------------------------------------------------


async def test_returns_nodes_and_edges_when_kg_available(monkeypatch):
    nodes = [
        {"id": "n1", "labels": ["Paradigm"], "props": {"name": "homeostatic"}},
        {"id": "n2", "labels": ["Postulate"], "props": {"id": "P1"}},
    ]
    edges = [
        {
            "id": "e1",
            "source": "n1",
            "target": "n2",
            "type": "BELONGS_TO",
            "props": {},
        }
    ]
    _set_services(monkeypatch, kg=_stub_kg(nodes, edges))

    body = await knowledge_graph()

    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1
    assert body["current_run_node_ids"] == []
    assert body["nodes"][0]["label"] == "Paradigm"
    assert body["edges"][0]["type"] == "BELONGS_TO"


# ---------------------------------------------------------------------------
# AC2 — run_id populates current_run_node_ids
# ---------------------------------------------------------------------------


async def test_run_id_populates_current_run_node_ids(monkeypatch):
    nodes = [
        {"id": "elem_n1", "labels": ["Paradigm"], "props": {"name": "homeostatic"}},
        {"id": "elem_n2", "labels": ["Postulate"], "props": {"id": "P1"}},
    ]
    _set_services(
        monkeypatch,
        kg=_stub_kg(nodes, []),
        db=_stub_db_with_observations([("Paradigm", "homeostatic")]),
    )

    body = await knowledge_graph(
        run_id="00000000-0000-0000-0000-000000000001"
    )

    assert body["current_run_node_ids"] == ["elem_n1"]


async def test_run_id_missing_returns_empty_highlight(monkeypatch):
    nodes = [{"id": "n1", "labels": ["Paradigm"], "props": {"name": "a"}}]
    _set_services(monkeypatch, kg=_stub_kg(nodes, []))

    body = await knowledge_graph()

    assert body["current_run_node_ids"] == []


async def test_invalid_run_id_returns_empty_highlight(monkeypatch):
    nodes = [{"id": "n1", "labels": ["Paradigm"], "props": {"name": "a"}}]
    _set_services(
        monkeypatch,
        kg=_stub_kg(nodes, []),
        db=_stub_db_with_observations([("Paradigm", "a")]),
    )

    body = await knowledge_graph(run_id="not-a-uuid")

    assert body["current_run_node_ids"] == []


# ---------------------------------------------------------------------------
# AC3 — label filter (deviation: spec said `namespace` but Neo4j nodes
# carry Cypher labels, not namespace props — see completion summary)
# ---------------------------------------------------------------------------


async def test_label_filter_keeps_only_matching_nodes(monkeypatch):
    nodes = [
        {"id": "n1", "labels": ["Paradigm"], "props": {"name": "a"}},
        {"id": "n2", "labels": ["Postulate"], "props": {"id": "P1"}},
    ]
    edges = [
        {"id": "e1", "source": "n1", "target": "n2", "type": "REL", "props": {}}
    ]
    _set_services(monkeypatch, kg=_stub_kg(nodes, edges))

    body = await knowledge_graph(label="Paradigm")

    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["label"] == "Paradigm"
    # Edge pointing to a filtered-out node must be dropped too
    assert body["edges"] == []


# ---------------------------------------------------------------------------
# AC4 — 503 when Neo4j unavailable
# ---------------------------------------------------------------------------


async def test_returns_503_when_kg_is_none(monkeypatch):
    _set_services(monkeypatch, kg=None)

    with pytest.raises(HTTPException) as exc:
        await knowledge_graph()

    assert exc.value.status_code == 503


async def test_returns_503_when_services_is_none(monkeypatch):
    monkeypatch.setattr(api_module, "_services", None)

    with pytest.raises(HTTPException) as exc:
        await knowledge_graph()

    assert exc.value.status_code == 503


async def test_returns_503_when_kg_query_raises(monkeypatch):
    kg = MagicMock()

    async def boom(_cypher: str):
        raise RuntimeError("Neo4j connection lost")

    kg.query = boom
    _set_services(monkeypatch, kg=kg)

    with pytest.raises(HTTPException) as exc:
        await knowledge_graph()

    assert exc.value.status_code == 503

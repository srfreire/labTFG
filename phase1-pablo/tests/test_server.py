"""Tests for decisionlab.server.ConnectionManager state tracking.

Doesn't start a real server — exercises the in-memory state machine directly
with a fake WebSocket so each emit() call is observable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from decisionlab.server import ConnectionManager, _filter_superseded_relations, app


def test_app_exists():
    assert app is not None
    # Confirms route registration on import (no raise)
    routes = [getattr(r, "path", None) for r in app.routes]
    assert "/ws" in routes


@pytest.fixture
def fake_ws():
    """A WebSocket double whose accept/close/send_json are async no-ops."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
def manager() -> ConnectionManager:
    return ConnectionManager()


@pytest.mark.asyncio
async def test_connect_accepts_ws(manager, fake_ws):
    await manager.connect(fake_ws)
    fake_ws.accept.assert_awaited_once()
    assert manager.ws is fake_ws


@pytest.mark.asyncio
async def test_connect_replaces_previous_client(manager):
    old = AsyncMock()
    new = AsyncMock()
    await manager.connect(old)
    await manager.connect(new)
    old.close.assert_awaited_once()
    new.accept.assert_awaited_once()
    assert manager.ws is new


@pytest.mark.asyncio
async def test_emit_node_add_appends_to_nodes(manager, fake_ws):
    await manager.connect(fake_ws)
    msg = {"type": "node_add", "node": {"id": "n1", "label": "Researcher"}}
    await manager.emit(msg)
    assert manager.nodes == [{"id": "n1", "label": "Researcher"}]
    fake_ws.send_json.assert_awaited_once_with(msg)


@pytest.mark.asyncio
async def test_emit_edge_add_appends_to_edges(manager, fake_ws):
    await manager.connect(fake_ws)
    edge = {"id": "e1", "source": "n1", "target": "n2"}
    await manager.emit({"type": "edge_add", "edge": edge})
    assert manager.edges == [edge]


@pytest.mark.asyncio
async def test_emit_node_update_modifies_existing_node(manager, fake_ws):
    await manager.connect(fake_ws)
    await manager.emit({"type": "node_add", "node": {"id": "n1", "status": "pending"}})
    await manager.emit({"type": "node_update", "id": "n1", "status": "running"})
    assert manager.nodes[0]["status"] == "running"


@pytest.mark.asyncio
async def test_emit_node_update_merges_metadata_for_reconnect(manager, fake_ws):
    await manager.connect(fake_ws)
    await manager.emit(
        {
            "type": "node_add",
            "node": {
                "id": "n1",
                "status": "running",
                "label": "old",
                "metadata": {"a": 1},
            },
        }
    )
    await manager.emit(
        {
            "type": "node_update",
            "id": "n1",
            "status": "done",
            "label": "new",
            "metadata": {"b": 2},
        }
    )

    assert manager.nodes[0]["status"] == "done"
    assert manager.nodes[0]["label"] == "new"
    assert manager.nodes[0]["metadata"] == {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_emit_node_update_unknown_id_is_noop(manager, fake_ws):
    await manager.connect(fake_ws)
    await manager.emit({"type": "node_update", "id": "missing", "status": "x"})
    assert manager.nodes == []


@pytest.mark.asyncio
async def test_emit_stage_records_current(manager, fake_ws):
    await manager.connect(fake_ws)
    await manager.emit({"type": "stage", "label": "RESEARCH"})
    assert manager.current_stage == "RESEARCH"


@pytest.mark.asyncio
async def test_emit_review_request_pinned_until_pipeline_done(manager, fake_ws):
    await manager.connect(fake_ws)
    pending = {"type": "review_request", "stage": "REVIEW_RESEARCH", "data": {}}
    await manager.emit(pending)
    assert manager.pending_review == pending

    await manager.emit({"type": "pipeline_done"})
    assert manager.pending_review is None


@pytest.mark.asyncio
async def test_review_response_clears_pending_review(manager, fake_ws, monkeypatch):
    await manager.connect(fake_ws)
    pending = {"type": "review_request", "stage": "review_research", "data": {}}
    await manager.emit(pending)

    dispatched = []

    def fake_dispatch(stage, data):
        dispatched.append((stage, data))

    monkeypatch.setattr(
        "decisionlab.web_feedback.handle_review_response", fake_dispatch
    )

    await manager.handle_review_response(
        {"type": "review_response", "stage": "review_research", "data": {"ok": True}}
    )

    assert dispatched == [("review_research", {"ok": True})]
    assert manager.pending_review is None


@pytest.mark.asyncio
async def test_emit_graph_clear_resets_collections(manager, fake_ws):
    await manager.connect(fake_ws)
    await manager.emit({"type": "node_add", "node": {"id": "n1"}})
    await manager.emit({"type": "edge_add", "edge": {"id": "e1"}})
    await manager.emit({"type": "graph_clear"})
    assert manager.nodes == []
    assert manager.edges == []


@pytest.mark.asyncio
async def test_emit_agrex_clear_resets_collections(manager, fake_ws):
    await manager.connect(fake_ws)
    await manager.emit({"type": "node_add", "node": {"id": "n1"}})
    await manager.emit({"type": "edge_add", "edge": {"id": "e1"}})
    await manager.emit({"type": "clear"})
    assert manager.nodes == []
    assert manager.edges == []


@pytest.mark.asyncio
async def test_emit_swallows_send_failure(manager, fake_ws):
    """If the WS send fails, emit() does NOT raise (allows pipeline to continue)."""
    fake_ws.send_json.side_effect = RuntimeError("disconnected")
    await manager.connect(fake_ws)
    await manager.emit({"type": "stage", "label": "DONE"})
    # No raise; state is still tracked
    assert manager.current_stage == "DONE"


@pytest.mark.asyncio
async def test_emit_with_no_ws_only_tracks_state(manager):
    """emit() doesn't crash when there's no WS attached."""
    await manager.emit({"type": "node_add", "node": {"id": "n1"}})
    assert manager.nodes == [{"id": "n1"}]


def test_reset_clears_state(manager):
    manager.nodes.append({"id": "x"})
    manager.edges.append({"id": "y"})
    manager.current_stage = "RESEARCH"
    manager.pending_review = {"type": "review_request"}
    manager.reset()
    assert manager.nodes == []
    assert manager.edges == []
    assert manager.current_stage is None
    assert manager.pending_review is None


# ---------------------------------------------------------------------------
# /api/kg/snapshot — superseded-relation filter (Issue 5)
# ---------------------------------------------------------------------------


def _make_rel(rid: str, memory_id: str | None) -> dict:
    """Build a relations-dict shaped like the snapshot endpoint emits."""
    props: dict = {}
    if memory_id is not None:
        props["memory_id"] = memory_id
    return {
        "id": rid,
        "source": "n1",
        "target": "n2",
        "type": "SUPPORTS",
        "run_id": None,
        "properties": props,
    }


def test_filter_superseded_keeps_only_valid_memory_ids():
    rels = [
        _make_rel("e-valid", "mem-1"),
        _make_rel("e-superseded", "mem-2"),
        _make_rel("e-also-valid", "mem-3"),
    ]
    valid = {"mem-1", "mem-3"}

    out = _filter_superseded_relations(rels, valid)

    assert [r["id"] for r in out] == ["e-valid", "e-also-valid"]


def test_filter_superseded_keeps_relations_without_memory_id():
    """Pre-P4-004 seed relations have no memory_id and must pass through."""
    rels = [
        _make_rel("e-seed", None),
        _make_rel("e-superseded", "mem-old"),
    ]
    valid = {"mem-new"}

    out = _filter_superseded_relations(rels, valid)

    assert [r["id"] for r in out] == ["e-seed"]


def test_filter_superseded_empty_valid_set_drops_all_with_memory_id():
    rels = [
        _make_rel("e-seed", None),
        _make_rel("e-1", "mem-1"),
        _make_rel("e-2", "mem-2"),
    ]

    out = _filter_superseded_relations(rels, set())

    assert [r["id"] for r in out] == ["e-seed"]


def test_filter_superseded_full_valid_set_keeps_all():
    """If valid_ids covers every memory_id, nothing is dropped — mirrors
    the include_superseded=True semantic (everything kept).
    """
    rels = [
        _make_rel("e-1", "mem-1"),
        _make_rel("e-2", "mem-2"),
        _make_rel("e-seed", None),
    ]

    out = _filter_superseded_relations(rels, {"mem-1", "mem-2"})

    assert [r["id"] for r in out] == ["e-1", "e-2", "e-seed"]


def test_filter_superseded_handles_missing_or_none_properties():
    """Defensive: a row with no/None ``properties`` shouldn't crash."""
    rels = [
        {"id": "e-no-props", "source": "n1", "target": "n2", "type": "X"},
        {
            "id": "e-empty-props",
            "source": "n1",
            "target": "n2",
            "type": "X",
            "properties": None,
        },
    ]

    out = _filter_superseded_relations(rels, set())

    assert [r["id"] for r in out] == ["e-no-props", "e-empty-props"]

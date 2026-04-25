"""Tests for decisionlab.server.ConnectionManager state tracking.

Doesn't start a real server — exercises the in-memory state machine directly
with a fake WebSocket so each emit() call is observable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from decisionlab.server import ConnectionManager, app


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
    # Root node_add events are buffered for one tick so a following spawn edge
    # can be folded into parent_id. Flush to commit it.
    await manager.flush_pending_node_add()
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
async def test_emit_node_update_unknown_id_is_noop(manager, fake_ws):
    await manager.connect(fake_ws)
    await manager.emit({"type": "node_update", "id": "missing", "status": "x"})
    assert manager.nodes == []


@pytest.mark.asyncio
async def test_emit_stage_change_records_current(manager, fake_ws):
    await manager.connect(fake_ws)
    await manager.emit({"type": "stage_change", "stage": "RESEARCH"})
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
async def test_emit_graph_clear_resets_collections(manager, fake_ws):
    await manager.connect(fake_ws)
    await manager.emit({"type": "node_add", "node": {"id": "n1"}})
    await manager.emit({"type": "edge_add", "edge": {"id": "e1"}})
    await manager.emit({"type": "graph_clear"})
    assert manager.nodes == []
    assert manager.edges == []


@pytest.mark.asyncio
async def test_emit_swallows_send_failure(manager, fake_ws):
    """If the WS send fails, emit() does NOT raise (allows pipeline to continue)."""
    fake_ws.send_json.side_effect = RuntimeError("disconnected")
    await manager.connect(fake_ws)
    await manager.emit({"type": "stage_change", "stage": "DONE"})
    # No raise; state is still tracked
    assert manager.current_stage == "DONE"


@pytest.mark.asyncio
async def test_emit_with_no_ws_only_tracks_state(manager):
    """emit() doesn't crash when there's no WS attached."""
    await manager.emit({"type": "node_add", "node": {"id": "n1"}})
    await manager.flush_pending_node_add()
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

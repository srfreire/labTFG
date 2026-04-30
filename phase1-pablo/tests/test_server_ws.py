"""End-to-end tests for the WebSocket endpoint at /ws.

Drives the actual ASGI app via Starlette's TestClient with a fake
``run_pipeline`` so the test deterministically controls what the pipeline
emits and when. Covers reconnection state recovery (state_sync ordering vs.
pending_review) and the concurrent-send hazard between an in-flight pipeline
emit and a fresh client's reconnect snapshot.

Companion to tests/test_server.py, which covers ConnectionManager state
bookkeeping with a fake WebSocket double.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

import decisionlab.server as server_mod
import shared  # type: ignore[import-not-found]
from decisionlab.server import ConnectionManager, app, manager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def stub_shared(monkeypatch):
    """No-op shared infra so the FastAPI lifespan doesn't try to reach
    Postgres / S3 / Neo4j during TestClient startup. The /ws endpoint itself
    doesn't depend on shared, so this is sufficient.
    """

    async def noop():
        return None

    monkeypatch.setattr(shared, "init", noop, raising=True)
    monkeypatch.setattr(shared, "shutdown", noop, raising=True)


@pytest.fixture(autouse=True)
def reset_manager_state():
    """Clear the module-global ConnectionManager between tests."""

    yield
    manager.pipeline_task = None
    manager.reset()
    manager.ws = None


def _drain_frames(ws, n: int, timeout: float = 2.0) -> list[dict]:
    """Read up to *n* JSON frames from *ws* within *timeout* seconds.

    ``receive_json()`` is unconditionally blocking. If the server only sends
    fewer than *n* frames, a naive loop hangs forever — this returns whatever
    arrived within the budget so the assertion can flag a missing frame
    instead of timing out the whole test session.
    """

    frames: list[dict] = []
    done = threading.Event()

    def reader() -> None:
        try:
            for _ in range(n):
                frames.append(ws.receive_json())
        except BaseException:
            pass
        finally:
            done.set()

    threading.Thread(target=reader, daemon=True).start()
    done.wait(timeout=timeout)
    return frames


# ---------------------------------------------------------------------------
# Bug #1 — concurrent emit + snapshot must serialize on a shared lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_emit_and_snapshot_do_not_interleave():
    """Pipeline emits and the reconnect-snapshot block must not produce
    overlapping ``ws.send_json`` calls — Starlette's WebSocket is not safe
    for concurrent send. The manager has to expose a lock that both
    ``_emit_raw`` and the snapshot block share.
    """

    in_flight = 0
    max_concurrent = 0

    async def slow_send_json(_msg: dict) -> None:
        nonlocal in_flight, max_concurrent
        in_flight += 1
        max_concurrent = max(max_concurrent, in_flight)
        await asyncio.sleep(0.005)
        in_flight -= 1

    fake_ws = AsyncMock()
    fake_ws.accept = AsyncMock()
    fake_ws.close = AsyncMock()
    fake_ws.send_json = slow_send_json

    mgr = ConnectionManager()
    await mgr.connect(fake_ws)

    async def pipeline_emit_burst() -> None:
        for i in range(8):
            await mgr.emit({"type": "node_add", "node": {"id": str(i)}})

    async def reconnect_snapshot() -> None:
        # Mirrors what websocket_endpoint's snapshot block does, holding the
        # same lock _emit_raw uses so the two paths serialize.
        async with mgr._send_lock:
            await fake_ws.send_json({"type": "run_start", "run_id": "x"})
            await fake_ws.send_json(
                {
                    "type": "state_sync",
                    "nodes": list(mgr.nodes),
                    "edges": list(mgr.edges),
                    "stage": mgr.current_stage,
                }
            )

    await asyncio.gather(pipeline_emit_burst(), reconnect_snapshot())

    assert max_concurrent == 1, (
        f"sends overlapped (max {max_concurrent} concurrent) — lock not held"
    )


# ---------------------------------------------------------------------------
# Baseline — reconnect mid-run returns run_start + state_sync
# ---------------------------------------------------------------------------


def test_reconnect_mid_run_returns_state_sync(monkeypatch):
    async def fake_pipeline(problem: str, emit, until_stage: Any = None) -> None:
        del problem, until_stage
        await emit({"type": "run_start", "run_id": "test-run-1"})
        await emit({"type": "node_add", "node": {"id": "n1", "label": "Researcher"}})
        await emit(
            {"type": "edge_add", "edge": {"id": "e1", "source": "n1", "target": "n2"}}
        )
        await emit({"type": "stage", "label": "research"})
        # Idle so the pipeline_task stays alive across the reconnect.
        await asyncio.sleep(60)

    monkeypatch.setattr(server_mod, "run_pipeline", fake_pipeline)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws1:
            ws1.send_json({"type": "start", "problem": "test"})
            for _ in range(4):
                ws1.receive_json()
        with client.websocket_connect("/ws") as ws2:
            frames = _drain_frames(ws2, n=2, timeout=2.0)

    types = [f["type"] for f in frames]
    assert "run_start" in types
    assert "state_sync" in types
    state_sync = next(f for f in frames if f["type"] == "state_sync")
    assert any(n["id"] == "n1" for n in state_sync["nodes"])
    assert any(e["id"] == "e1" for e in state_sync["edges"])
    assert state_sync["stage"] == "research"


# ---------------------------------------------------------------------------
# Bug #2 — reconnect during pending review returns BOTH snapshot and prompt
# ---------------------------------------------------------------------------


def test_reconnect_during_review_returns_snapshot_then_prompt(monkeypatch):
    async def fake_pipeline(problem: str, emit, until_stage: Any = None) -> None:
        del problem, until_stage
        await emit({"type": "run_start", "run_id": "test-run-2"})
        await emit({"type": "node_add", "node": {"id": "n1", "label": "Researcher"}})
        await emit({"type": "stage", "label": "research"})
        await emit(
            {
                "type": "review_request",
                "stage": "review_research",
                "data": {"paradigms": []},
            }
        )
        await asyncio.sleep(60)

    monkeypatch.setattr(server_mod, "run_pipeline", fake_pipeline)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws1:
            ws1.send_json({"type": "start", "problem": "test"})
            for _ in range(4):
                ws1.receive_json()
        with client.websocket_connect("/ws") as ws2:
            frames = _drain_frames(ws2, n=3, timeout=2.0)

    types = [f["type"] for f in frames]
    # Buggy code only sends [run_start, review_request]; without the graph
    # snapshot, the UI would render the review prompt over an empty graph.
    assert types == ["run_start", "state_sync", "review_request"], (
        f"reconnect-during-review must send graph snapshot before the prompt; got {types}"
    )
    state_sync = frames[1]
    assert any(n["id"] == "n1" for n in state_sync["nodes"])
    assert state_sync["stage"] == "research"

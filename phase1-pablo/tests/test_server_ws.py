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
from decisionlab import web_feedback
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
    from unittest.mock import MagicMock

    from shared.services import Services

    fake_services = Services(
        db=MagicMock(),
        storage=MagicMock(),
        kg=None,
        vectors=None,
        embeddings=None,
    )

    async def fake_init_services(_settings=None):
        return fake_services

    async def fake_shutdown_services(_services):
        return None

    monkeypatch.setattr(server_mod, "init_services", fake_init_services)
    monkeypatch.setattr(server_mod, "shutdown_services", fake_shutdown_services)


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


def test_hitl_review_response_roundtrip_unblocks_pipeline(monkeypatch):
    """A real WS ``review_response`` frame must reach the coroutine waiting
    inside ``web_feedback.wait_for_review``.

    This is the core HITL contract: the pipeline emits a prompt, the frontend
    answers over the same socket, and the agent pipeline continues.
    """

    stages = [
        "review_research",
        "review_formalize",
        "get_env_spec",
        "review_reason",
        "review_build",
    ]

    async def fake_pipeline(problem: str, emit, until_stage: Any = None) -> None:
        del problem, until_stage
        await emit({"type": "run_start", "run_id": "hitl-test-run"})
        for stage in stages:
            response = await web_feedback.wait_for_review(
                stage,
                emit,
                {"prompt": stage},
            )
            await emit(
                {
                    "type": "hitl_ack",
                    "stage": stage,
                    "response": response,
                }
            )

    monkeypatch.setattr(server_mod, "run_pipeline", fake_pipeline)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start", "problem": "test hitl"})

        run_start = ws.receive_json()
        assert run_start == {"type": "run_start", "run_id": "hitl-test-run"}

        for stage in stages:
            prompt = ws.receive_json()
            assert prompt["type"] == "review_request"
            assert prompt["stage"] == stage
            assert prompt["data"] == {"prompt": stage}

            payload = {"approved": [stage], "selected": {stage: [1]}}
            ws.send_json(
                {
                    "type": "review_response",
                    "stage": stage,
                    "data": payload,
                }
            )

            ack = ws.receive_json()
            assert ack == {
                "type": "hitl_ack",
                "stage": stage,
                "response": payload,
            }


# ---------------------------------------------------------------------------
# Bug #3 — receive loop must survive malformed input
# ---------------------------------------------------------------------------


def test_malformed_json_does_not_kill_endpoint(monkeypatch):
    """A frame that isn't valid JSON used to crash the receive loop because
    only WebSocketDisconnect was caught. The endpoint should survive and
    keep responding to subsequent valid messages.
    """

    async def fake_pipeline(problem: str, emit, until_stage: Any = None) -> None:
        del problem, until_stage
        await emit({"type": "node_add", "node": {"id": "after-bad-json"}})
        await asyncio.sleep(60)

    monkeypatch.setattr(server_mod, "run_pipeline", fake_pipeline)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_text("definitely not json {")
        err = ws.receive_json()
        assert err["type"] == "error"

        # Endpoint still alive — a valid `start` should drive the pipeline.
        ws.send_json({"type": "start", "problem": "post-malformed"})
        f = ws.receive_json()
        assert f["type"] == "node_add"
        assert f["node"]["id"] == "after-bad-json"


def test_start_without_problem_returns_error_frame():
    """`start` requires `problem`. Without it the old code would KeyError
    and kill the endpoint. The new code should reply with an error frame
    and keep the connection open.
    """

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start"})  # no `problem` field
        err = ws.receive_json()
        assert err["type"] == "error"

        # Survival check — sending another bad frame should also produce
        # an error, not a disconnect.
        ws.send_json({"type": "start"})
        err2 = ws.receive_json()
        assert err2["type"] == "error"


# ---------------------------------------------------------------------------
# Bug #4 — `start` while a pipeline is running must await the prior cancel
# ---------------------------------------------------------------------------


def test_double_start_cancels_first_pipeline_cleanly(monkeypatch):
    """When a second `start` arrives, the first pipeline_task must be
    cancelled AND awaited before the new task is created — otherwise the
    old task's tail (closing emits, trace flush) overlaps with the new
    task's first events on the same manager.
    """

    cancelled = threading.Event()

    async def fake_pipeline_1(problem: str, emit, until_stage: Any = None) -> None:
        del problem, until_stage
        try:
            await emit({"type": "node_add", "node": {"id": "from-pipe-1"}})
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            # Simulate slow finalization (state.save() in the real pipeline).
            # Without cancel-await, pipe-2's first frame races this and the
            # cancelled event is not yet set when the test reads it.
            await asyncio.sleep(0.1)
            cancelled.set()
            raise

    async def fake_pipeline_2(problem: str, emit, until_stage: Any = None) -> None:
        del problem, until_stage
        await emit({"type": "node_add", "node": {"id": "from-pipe-2"}})
        await asyncio.sleep(60)

    pipelines = [fake_pipeline_1, fake_pipeline_2]
    call_count = [0]

    async def picker(problem: str, emit, until_stage: Any = None) -> None:
        idx = call_count[0]
        call_count[0] += 1
        await pipelines[idx](problem, emit, until_stage=until_stage)

    monkeypatch.setattr(server_mod, "run_pipeline", picker)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start", "problem": "first"})
        f1 = ws.receive_json()
        assert f1["node"]["id"] == "from-pipe-1"

        task1 = manager.pipeline_task
        assert task1 is not None and not task1.done()

        ws.send_json({"type": "start", "problem": "second"})
        f2 = ws.receive_json()
        assert f2["node"]["id"] == "from-pipe-2"

    # By the time the second pipeline emits its first frame, the first
    # task must already be done (i.e. its cancellation was awaited).
    assert task1.done(), "first pipeline_task must be done before pipe-2 emits"
    assert manager.pipeline_task is not task1
    assert cancelled.is_set(), "fake_pipeline_1 must have observed CancelledError"


# ---------------------------------------------------------------------------
# Bug #5 — lifespan teardown must cancel and await pipeline_task
# ---------------------------------------------------------------------------


def test_lifespan_shutdown_cancels_running_pipeline(monkeypatch):
    """When the FastAPI app shuts down (Ctrl-C, SIGTERM, test-client exit)
    the lifespan teardown must cancel and await any still-running pipeline
    BEFORE ``shutdown_services()`` — otherwise the task hangs onto the LLM
    client, DB session, and trace.jsonl writer until the loop is force-closed.

    Asserts state captured inside the ``shutdown_services`` hook (which runs
    immediately after the cancel-await in the lifespan's finally block).
    Without the fix the captured task would still be pending.
    """

    cancelled = threading.Event()
    captured: dict = {}

    async def fake_pipeline(problem: str, emit, until_stage: Any = None) -> None:
        del problem, until_stage
        try:
            await emit({"type": "node_add", "node": {"id": "running"}})
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def shutdown_capture(_services=None):
        task = manager.pipeline_task
        captured["task_done"] = task.done() if task is not None else None
        captured["cancelled"] = cancelled.is_set()

    monkeypatch.setattr(server_mod, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(server_mod, "shutdown_services", shutdown_capture)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "start", "problem": "test"})
        # Drain the first frame so we know the pipeline really is running
        # before we let the contexts unwind.
        ws.receive_json()

    assert captured.get("task_done") is True, (
        "lifespan must cancel + await pipeline_task before shutdown_services — "
        f"captured={captured}"
    )
    assert captured.get("cancelled") is True, (
        "fake_pipeline should have observed CancelledError before shutdown"
    )

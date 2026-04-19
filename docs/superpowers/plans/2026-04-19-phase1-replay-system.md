# Phase 1 Replay System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every pipeline WS event to S3, expose it via REST, and add a floating timeline + past-runs list so runs can be replayed with real timings or step-by-step.

**Architecture:** Server stamps and batches events into `research/{run_id}/events.jsonl`. Frontend reuses the existing WS reducer to *derive* graph state from events, fed either live or from a REST fetch of the recorded stream. A single floating `<Timeline />` drives live pin-to-latest, pause-and-scrub, and past-run replay.

**Tech Stack:** FastAPI · SQLAlchemy async · Alembic · MinIO/S3 · aioboto3 · React · Vite · Vitest · pytest · Playwright.

**Spec:** `docs/superpowers/specs/2026-04-19-phase1-replay-system-design.md`.

---

## Conventions

- **All paths are relative to the repo root** `/Users/ppazosp/projects/labTFG/`.
- **Python package root:** `phase1-pablo/src/decisionlab/`.
- **Python tests root:** `phase1-pablo/tests/`.
- **Web root:** `phase1-pablo/web/`.
- **Run pytest from** `phase1-pablo/` via `uv run pytest ...`.
- **Run web commands from** `phase1-pablo/web/` via `pnpm ...`.
- **Commit syntax** (per repo): `<feat|fix>[<module>]: <message>`. Module is one of `decisionlab`, `web`, `docs`, `shared`.

---

## Task 1: `EventLogger` helper — pure-logic tests first

**Files:**
- Create: `phase1-pablo/src/decisionlab/runtime/event_logger.py`
- Test:   `phase1-pablo/tests/test_event_logger.py`

Responsibility: own a batch buffer; decide when to flush based on size (50) or age (2 s); render the buffer as NDJSON; no S3 coupling (a caller injects a flush callback).

- [ ] **Step 1: Write the failing test for batch-size trigger**

`phase1-pablo/tests/test_event_logger.py`:

```python
import asyncio

import pytest

from decisionlab.runtime.event_logger import EventLogger


@pytest.mark.asyncio
async def test_flushes_when_batch_reaches_size_limit() -> None:
    flushed: list[str] = []

    async def on_flush(payload: str) -> None:
        flushed.append(payload)

    logger = EventLogger(on_flush=on_flush, max_batch=3, max_age_s=60.0)
    await logger.add({"type": "node_add", "node": {"id": "a"}})
    await logger.add({"type": "node_add", "node": {"id": "b"}})
    assert flushed == []  # below threshold
    await logger.add({"type": "node_add", "node": {"id": "c"}})
    # reaching the threshold triggers a flush synchronously
    assert len(flushed) == 1
    # payload is NDJSON: one JSON object per line, trailing newline
    lines = flushed[0].rstrip("\n").split("\n")
    assert len(lines) == 3
    assert '"id": "a"' in lines[0]
    assert '"id": "c"' in lines[2]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd phase1-pablo && uv run pytest tests/test_event_logger.py::test_flushes_when_batch_reaches_size_limit -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'decisionlab.runtime.event_logger'`.

- [ ] **Step 3: Implement the minimal `EventLogger`**

`phase1-pablo/src/decisionlab/runtime/event_logger.py`:

```python
"""Batch-buffering helper for pipeline event persistence.

Decouples batching policy from the storage backend. The caller supplies an
async ``on_flush`` callback that receives an NDJSON payload to persist.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Awaitable, Callable

FlushFn = Callable[[str], Awaitable[None]]


class EventLogger:
    def __init__(
        self,
        on_flush: FlushFn,
        max_batch: int = 50,
        max_age_s: float = 2.0,
    ) -> None:
        self._on_flush = on_flush
        self._max_batch = max_batch
        self._max_age_s = max_age_s
        self._buf: list[dict] = []
        self._buf_started_at: float | None = None
        self._lock = asyncio.Lock()

    async def add(self, event: dict) -> None:
        """Append *event*; flush synchronously if the batch is full."""
        async with self._lock:
            if not self._buf:
                self._buf_started_at = time.monotonic()
            self._buf.append(event)
            if len(self._buf) >= self._max_batch:
                await self._flush_locked()

    async def flush(self) -> None:
        """Flush whatever is buffered. Safe to call with nothing pending."""
        async with self._lock:
            await self._flush_locked()

    def is_due(self) -> bool:
        """Return True if age-based flush is due."""
        if not self._buf or self._buf_started_at is None:
            return False
        return (time.monotonic() - self._buf_started_at) >= self._max_age_s

    async def _flush_locked(self) -> None:
        if not self._buf:
            return
        payload = "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in self._buf)
        self._buf.clear()
        self._buf_started_at = None
        await self._on_flush(payload)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd phase1-pablo && uv run pytest tests/test_event_logger.py -v
```

Expected: PASS.

- [ ] **Step 5: Add the remaining unit tests (age trigger, empty flush, concurrent adds)**

Append to `phase1-pablo/tests/test_event_logger.py`:

```python
@pytest.mark.asyncio
async def test_age_trigger_reports_due_without_new_events() -> None:
    flushed: list[str] = []

    async def on_flush(payload: str) -> None:
        flushed.append(payload)

    logger = EventLogger(on_flush=on_flush, max_batch=100, max_age_s=0.01)
    await logger.add({"type": "node_add"})
    assert logger.is_due() is False
    await asyncio.sleep(0.02)
    assert logger.is_due() is True
    await logger.flush()
    assert len(flushed) == 1
    assert logger.is_due() is False  # buffer empty


@pytest.mark.asyncio
async def test_flush_on_empty_buffer_is_noop() -> None:
    calls = 0

    async def on_flush(payload: str) -> None:
        nonlocal calls
        calls += 1

    logger = EventLogger(on_flush=on_flush)
    await logger.flush()
    assert calls == 0


@pytest.mark.asyncio
async def test_concurrent_adds_respect_batch_size() -> None:
    flushed: list[str] = []

    async def on_flush(payload: str) -> None:
        flushed.append(payload)

    logger = EventLogger(on_flush=on_flush, max_batch=10, max_age_s=60.0)
    await asyncio.gather(*[logger.add({"i": i}) for i in range(30)])
    await logger.flush()
    # 30 events / batch 10 → exactly 3 size-triggered flushes; final explicit flush is a no-op
    assert len(flushed) == 3
    for payload in flushed:
        assert payload.count("\n") == 10
```

- [ ] **Step 6: Run the full test file to verify it passes**

```bash
cd phase1-pablo && uv run pytest tests/test_event_logger.py -v
```

Expected: 4 PASSED.

- [ ] **Step 7: Commit**

```bash
cd phase1-pablo
git add src/decisionlab/runtime/event_logger.py tests/test_event_logger.py
git commit -m "feat[decisionlab]: EventLogger batch buffer for WS event persistence"
```

---

## Task 2: `S3EventStore` — append semantics on top of MinIO

**Files:**
- Create: `phase1-pablo/src/decisionlab/runtime/event_store.py`
- Test:   `phase1-pablo/tests/test_event_store.py`

Responsibility: translate NDJSON batches from `EventLogger` into read-existing + put-new S3 operations. Isolated so we can fake it in unit tests.

- [ ] **Step 1: Write the failing test**

`phase1-pablo/tests/test_event_store.py`:

```python
import pytest

from decisionlab.runtime.event_store import S3EventStore


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, str] = {}
        self.put_calls: int = 0
        self.get_calls: int = 0

    async def get_text(self, key: str) -> str:
        self.get_calls += 1
        if key not in self.objects:
            raise KeyError(key)
        return self.objects[key]

    async def put_text(self, key: str, text: str, content_type: str = "text/plain") -> str:
        self.put_calls += 1
        self.objects[key] = text
        return key

    async def exists(self, key: str) -> bool:
        return key in self.objects


@pytest.mark.asyncio
async def test_first_append_creates_object() -> None:
    storage = FakeStorage()
    store = S3EventStore(storage, run_id="abc")
    await store.append('{"seq":1,"type":"node_add"}\n')
    assert storage.objects["research/abc/events.jsonl"] == '{"seq":1,"type":"node_add"}\n'
    assert storage.put_calls == 1


@pytest.mark.asyncio
async def test_subsequent_appends_concatenate() -> None:
    storage = FakeStorage()
    store = S3EventStore(storage, run_id="abc")
    await store.append('{"seq":1}\n')
    await store.append('{"seq":2}\n{"seq":3}\n')
    assert storage.objects["research/abc/events.jsonl"] == '{"seq":1}\n{"seq":2}\n{"seq":3}\n'


@pytest.mark.asyncio
async def test_caches_existing_content_after_first_load() -> None:
    storage = FakeStorage()
    storage.objects["research/abc/events.jsonl"] = '{"seq":0}\n'
    store = S3EventStore(storage, run_id="abc")
    await store.append('{"seq":1}\n')
    await store.append('{"seq":2}\n')
    # Only one get — subsequent appends use the cached tail
    assert storage.get_calls == 1
    assert storage.objects["research/abc/events.jsonl"] == '{"seq":0}\n{"seq":1}\n{"seq":2}\n'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd phase1-pablo && uv run pytest tests/test_event_store.py -v
```

Expected: FAIL (module missing).

- [ ] **Step 3: Implement `S3EventStore`**

`phase1-pablo/src/decisionlab/runtime/event_store.py`:

```python
"""Persist NDJSON event batches to S3 with read-then-put append semantics.

The S3 backend has no native append. We keep the full object body in memory
(cached after first load) and PUT the concatenated bytes on every append.
Acceptable at pipeline-event volumes (hundreds to low thousands per run).
"""
from __future__ import annotations

from typing import Protocol


class _StorageLike(Protocol):
    async def get_text(self, key: str) -> str: ...
    async def put_text(self, key: str, text: str, content_type: str = "text/plain") -> str: ...
    async def exists(self, key: str) -> bool: ...


class S3EventStore:
    CONTENT_TYPE = "application/x-ndjson"

    def __init__(self, storage: _StorageLike, run_id: str) -> None:
        self._storage = storage
        self._key = f"research/{run_id}/events.jsonl"
        self._tail: str | None = None  # cached full body

    async def append(self, ndjson_chunk: str) -> None:
        if self._tail is None:
            if await self._storage.exists(self._key):
                self._tail = await self._storage.get_text(self._key)
            else:
                self._tail = ""
        self._tail = self._tail + ndjson_chunk
        await self._storage.put_text(self._key, self._tail, self.CONTENT_TYPE)

    @property
    def key(self) -> str:
        return self._key
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd phase1-pablo && uv run pytest tests/test_event_store.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
cd phase1-pablo
git add src/decisionlab/runtime/event_store.py tests/test_event_store.py
git commit -m "feat[decisionlab]: S3EventStore append-via-read-put for event logs"
```

---

## Task 3: Integrate logging into `ConnectionManager`

**Files:**
- Modify: `phase1-pablo/src/decisionlab/server.py`
- Test:   `phase1-pablo/tests/test_server_event_log.py`

Responsibility: on every `emit()`, stamp `seq` + `ts`, append to the logger. Flush on `pipeline_done`, `error`, cancel, and new `graph_clear`.

- [ ] **Step 1: Write the failing integration test**

`phase1-pablo/tests/test_server_event_log.py`:

```python
import json
import pytest

from decisionlab.server import ConnectionManager


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, str] = {}

    async def get_text(self, key: str) -> str:
        return self.objects[key]

    async def put_text(self, key: str, text: str, content_type: str = "text/plain") -> str:
        self.objects[key] = text
        return key

    async def exists(self, key: str) -> bool:
        return key in self.objects


@pytest.mark.asyncio
async def test_emit_stamps_and_persists_events() -> None:
    storage = FakeStorage()
    mgr = ConnectionManager(storage=storage)
    await mgr.emit({"type": "run_start", "run_id": "r1"})
    await mgr.emit({"type": "stage_change", "stage": "research", "status": "running"})
    await mgr.emit({"type": "node_add", "node": {"id": "n1", "kind": "agent", "label": "r", "status": "running", "meta": {}}})
    await mgr.emit({"type": "pipeline_done"})  # triggers a flush

    body = storage.objects["research/r1/events.jsonl"]
    lines = [json.loads(ln) for ln in body.strip().split("\n")]
    assert [e["type"] for e in lines] == [
        "run_start",
        "stage_change",
        "node_add",
        "pipeline_done",
    ]
    # Monotonic seq starting at 1, non-decreasing ts
    assert [e["seq"] for e in lines] == [1, 2, 3, 4]
    assert all(isinstance(e["ts"], (int, float)) for e in lines)
    for a, b in zip(lines, lines[1:]):
        assert a["ts"] <= b["ts"]


@pytest.mark.asyncio
async def test_cancel_flushes_partial_log() -> None:
    storage = FakeStorage()
    mgr = ConnectionManager(storage=storage)
    await mgr.emit({"type": "run_start", "run_id": "r2"})
    await mgr.emit({"type": "node_add", "node": {"id": "n1", "kind": "agent", "label": "r", "status": "running", "meta": {}}})
    await mgr.cancel_and_flush()
    body = storage.objects["research/r2/events.jsonl"]
    assert body.count("\n") == 2


@pytest.mark.asyncio
async def test_graph_clear_flushes_previous_run() -> None:
    storage = FakeStorage()
    mgr = ConnectionManager(storage=storage)
    await mgr.emit({"type": "run_start", "run_id": "r1"})
    await mgr.emit({"type": "node_add", "node": {"id": "n1", "kind": "agent", "label": "a", "status": "running", "meta": {}}})
    await mgr.emit({"type": "graph_clear"})  # closes r1
    await mgr.emit({"type": "run_start", "run_id": "r2"})
    await mgr.emit({"type": "pipeline_done"})
    # r1 has 3 events (run_start, node_add, graph_clear), r2 has 2 (run_start, pipeline_done)
    assert storage.objects["research/r1/events.jsonl"].count("\n") == 3
    assert storage.objects["research/r2/events.jsonl"].count("\n") == 2
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd phase1-pablo && uv run pytest tests/test_server_event_log.py -v
```

Expected: FAIL — `ConnectionManager` does not take `storage=` nor have `cancel_and_flush()`.

- [ ] **Step 3: Modify `ConnectionManager` in `phase1-pablo/src/decisionlab/server.py`**

Replace the `ConnectionManager` class (currently at lines 47–107 of `server.py`) with this version; leave the rest of the module alone for now:

```python
class ConnectionManager:
    """Manages the single WebSocket connection and tracks graph state for
    reconnection, and persists the event stream for replay."""

    def __init__(self, storage=None) -> None:
        self.ws: WebSocket | None = None
        self.pipeline_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.current_stage: str | None = None
        self.pending_review: dict | None = None
        self.run_id: str | None = None

        # -- event log --
        self._storage = storage  # None in tests that don't care
        self._seq: int = 0
        self._logger = None  # type: EventLogger | None
        self._store = None   # type: S3EventStore | None

    async def connect(self, ws: WebSocket) -> None:
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
        await ws.accept()
        self.ws = ws

    def _storage_or_none(self):
        if self._storage is not None:
            return self._storage
        try:
            import shared
            return getattr(shared, "storage", None)
        except Exception:
            return None

    def _ensure_logger(self, run_id: str) -> None:
        """Create a fresh logger + store pair for *run_id*."""
        from decisionlab.runtime.event_logger import EventLogger
        from decisionlab.runtime.event_store import S3EventStore

        storage = self._storage_or_none()
        if storage is None:
            self._logger = None
            self._store = None
            return
        self._store = S3EventStore(storage, run_id=run_id)
        self._logger = EventLogger(on_flush=self._store.append)

    async def _flush_log(self) -> None:
        if self._logger is not None:
            try:
                await self._logger.flush()
            except Exception as exc:  # best-effort persistence
                logger.warning("event log flush failed: %s", exc)

    async def emit(self, msg: dict) -> None:
        """Send *msg* to the WS client, track state for reconnection, and
        persist a stamped copy to the event log."""
        import time

        msg_type = msg.get("type")

        # Start a new logger when a new run_start arrives.
        if msg_type == "run_start":
            await self._flush_log()
            self._seq = 0
            self._ensure_logger(msg["run_id"])

        # -- state bookkeeping (unchanged from before) --
        if msg_type == "node_add":
            self.nodes.append(msg["node"])
        elif msg_type == "edge_add":
            self.edges.append(msg["edge"])
        elif msg_type == "node_update":
            for n in self.nodes:
                if n["id"] == msg["id"]:
                    n["status"] = msg["status"]
                    break
        elif msg_type == "stage_change":
            self.current_stage = msg.get("stage")
        elif msg_type == "review_request":
            self.pending_review = msg
        elif msg_type == "graph_clear":
            self.nodes.clear()
            self.edges.clear()
        elif msg_type == "run_start":
            self.run_id = msg.get("run_id")
        elif msg_type == "pipeline_done":
            self.pending_review = None

        # -- stamp + persist --
        if self._logger is not None:
            self._seq += 1
            stamped = {"seq": self._seq, "ts": int(time.time() * 1000), **msg}
            try:
                await self._logger.add(stamped)
            except Exception as exc:
                logger.warning("event log append failed: %s", exc)

        # -- send over WS (unstamped) --
        if self.ws is not None:
            try:
                await self.ws.send_json(msg)
            except Exception:
                pass

        # -- flush on terminal events --
        if msg_type in ("pipeline_done", "error", "graph_clear"):
            await self._flush_log()

    async def cancel_and_flush(self) -> None:
        """Call when a run is cancelled; persists the partial log."""
        await self._flush_log()

    def reset(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.current_stage = None
        self.pending_review = None
        self.run_id = None
        # NOTE: logger is reset on the next run_start emit.
```

Also update the `cancel` branch of the WS receive loop inside `websocket_endpoint` (currently around `server.py:159-162`):

```python
            elif msg_type == "cancel":
                if manager.pipeline_task and not manager.pipeline_task.done():
                    manager.pipeline_task.cancel()
                    await manager.cancel_and_flush()
                    manager.reset()
```

- [ ] **Step 4: Run the test suite to verify it passes**

```bash
cd phase1-pablo && uv run pytest tests/test_server_event_log.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Run the full existing server tests to ensure no regressions**

```bash
cd phase1-pablo && uv run pytest tests/test_server.py -v
```

Expected: pre-existing results unchanged (no new failures).

- [ ] **Step 6: Commit**

```bash
cd phase1-pablo
git add src/decisionlab/server.py tests/test_server_event_log.py
git commit -m "feat[decisionlab]: persist WS event stream to S3 per run"
```

---

## Task 4: Emit `review_decision` events

**Files:**
- Modify: `phase1-pablo/src/decisionlab/server.py`
- Modify: `phase1-pablo/src/decisionlab/web_feedback.py` *(inspect first — may not need changes)*
- Test:   `phase1-pablo/tests/test_server_event_log.py` (append)

Goal: when the server receives a `review_response` from the client, emit `{"type":"review_decision","stage":...,"approved":{...}}` so approvals are part of the recorded stream.

- [ ] **Step 1: Inspect `web_feedback.handle_review_response` signature**

```bash
sed -n '1,80p' phase1-pablo/src/decisionlab/web_feedback.py
```

Confirm it returns either `None` or a parsed payload. The emit in Step 3 uses the *raw* `data` from the WS message, which is already `{approved: {slug: bool}, ...}` shape for research/formalize/reason/build reviews (see `ClientMessage` in `types.ts`). No changes to `web_feedback.py` required.

- [ ] **Step 2: Write the failing test (append to existing file)**

Append to `phase1-pablo/tests/test_server_event_log.py`:

```python
@pytest.mark.asyncio
async def test_review_decision_emitted_on_review_response() -> None:
    storage = FakeStorage()
    mgr = ConnectionManager(storage=storage)
    await mgr.emit({"type": "run_start", "run_id": "r3"})
    await mgr.handle_review_response(
        {"stage": "review_research", "data": {"approved": {"homeostatic": True}}}
    )
    await mgr._flush_log()
    body = storage.objects["research/r3/events.jsonl"]
    lines = [json.loads(ln) for ln in body.strip().split("\n")]
    decisions = [e for e in lines if e["type"] == "review_decision"]
    assert len(decisions) == 1
    assert decisions[0]["stage"] == "review_research"
    assert decisions[0]["approved"] == {"homeostatic": True}
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd phase1-pablo && uv run pytest tests/test_server_event_log.py::test_review_decision_emitted_on_review_response -v
```

Expected: FAIL — no `handle_review_response` on the manager.

- [ ] **Step 4: Add `handle_review_response` on `ConnectionManager` in `server.py`**

Inside the `ConnectionManager` class, add:

```python
    async def handle_review_response(self, data: dict) -> None:
        """Record the user's review decision in the event stream and dispatch
        it to the waiting pipeline."""
        from decisionlab.web_feedback import handle_review_response as _dispatch

        stage = data["stage"]
        payload = data["data"]
        # Extract the approved map (varies by stage shape). Keep as-is when
        # unavailable so replays still see the raw payload.
        approved = payload.get("approved") if isinstance(payload, dict) else None
        await self.emit(
            {
                "type": "review_decision",
                "stage": stage,
                "approved": approved if approved is not None else payload,
            }
        )
        _dispatch(stage, payload)
```

Replace the existing `review_response` branch in the WS receive loop (currently in `server.py:154-157`) with:

```python
            elif msg_type == "review_response":
                await manager.handle_review_response(data)
```

- [ ] **Step 5: Run tests and verify they pass**

```bash
cd phase1-pablo && uv run pytest tests/test_server_event_log.py -v
```

Expected: 4 PASSED.

- [ ] **Step 6: Commit**

```bash
cd phase1-pablo
git add src/decisionlab/server.py tests/test_server_event_log.py
git commit -m "feat[decisionlab]: emit review_decision events for replay"
```

---

## Task 5: Add `Run.artifact_count` column + Alembic migration

**Files:**
- Modify: `shared/shared/models.py`
- Create: `shared/migrations/versions/<new_rev>_run_artifact_count.py`

Responsibility: denormalize the "how many models were built" count onto `Run` so the runs-list endpoint is a single SELECT.

- [ ] **Step 1: Check current Alembic head**

```bash
cd shared && uv run alembic heads
```

Expected: `a1b2c3d4e5f6 (head)`.

- [ ] **Step 2: Generate a new migration stub**

```bash
cd shared && uv run alembic revision -m "run_artifact_count"
```

This creates `shared/migrations/versions/<hash>_run_artifact_count.py` with `down_revision` already pointing at `a1b2c3d4e5f6`.

- [ ] **Step 3: Fill in the migration**

Replace the generated `upgrade` and `downgrade` with:

```python
def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("artifact_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runs", "artifact_count")
```

- [ ] **Step 4: Update the ORM model**

Modify `shared/shared/models.py`, inside `class Run`, after the `s3_prefix` column:

```python
    artifact_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
```

- [ ] **Step 5: Apply the migration**

```bash
cd shared && uv run alembic upgrade head
```

Expected: output ends with `Running upgrade a1b2c3d4e5f6 -> <new_rev>, run_artifact_count`.

- [ ] **Step 6: Verify by inspecting the table**

```bash
cd shared && uv run python -c "
import asyncio
from sqlalchemy import inspect
from shared.database import DatabaseService
from shared.settings import get_settings

async def main():
    db = DatabaseService(get_settings())
    await db.connect()
    async with db.engine.connect() as c:
        cols = await c.run_sync(lambda s: [c['name'] for c in inspect(s).get_columns('runs')])
        print(cols)
    await db.close()

asyncio.run(main())
"
```

Expected: list includes `artifact_count`.

- [ ] **Step 7: Commit**

```bash
git add shared/shared/models.py shared/migrations/versions/
git commit -m "feat[shared]: add Run.artifact_count column"
```

---

## Task 6: Populate `artifact_count` on pipeline completion

**Files:**
- Modify: `phase1-pablo/src/decisionlab/server.py` (the `run_pipeline` function)
- Test:   `phase1-pablo/tests/test_server.py` *(append a minimal integration probe)*

Responsibility: set `artifact_count = len(state.build_results)` when the pipeline transitions to `done`; set `status = "cancelled"` on cancel; set `status = "failed"` on exception.

- [ ] **Step 1: Modify `run_pipeline` in `server.py`**

In `run_pipeline` (`server.py:173` onward), after `await router.run()` inside the try-block, change the success-update block:

```python
            await router.run()
            async with shared.db.get_session() as session:
                from sqlalchemy import update

                await session.execute(
                    update(Run)
                    .where(Run.id == uuid.UUID(run_id))
                    .values(
                        status="done",
                        s3_report_key=f"research/{run_id}/report.md",
                        artifact_count=len(state.build_results),
                    )
                )
                await session.commit()
            await emit({"type": "pipeline_done"})
```

Extend the `except asyncio.CancelledError:` branch:

```python
        except asyncio.CancelledError:
            await state.save()
            async with shared.db.get_session() as session:
                from sqlalchemy import update
                await session.execute(
                    update(Run).where(Run.id == uuid.UUID(run_id)).values(status="cancelled")
                )
                await session.commit()
            raise
```

Extend the generic `except Exception:` branch:

```python
        except Exception as exc:
            logger.exception("Pipeline failed")
            try:
                async with shared.db.get_session() as session:
                    from sqlalchemy import update
                    await session.execute(
                        update(Run).where(Run.id == uuid.UUID(run_id)).values(status="failed")
                    )
                    await session.commit()
            except Exception:
                logger.debug("Could not mark run as failed")
            await emit({"type": "error", "message": str(exc)})
```

- [ ] **Step 2: Smoke-run the existing server tests to ensure no import-time regressions**

```bash
cd phase1-pablo && uv run pytest tests/test_server.py -v
```

Expected: pre-existing results unchanged.

- [ ] **Step 3: Commit**

```bash
cd phase1-pablo
git add src/decisionlab/server.py
git commit -m "feat[decisionlab]: update Run status/artifact_count on terminal transitions"
```

---

## Task 7: `GET /api/runs` endpoint

**Files:**
- Modify: `phase1-pablo/src/decisionlab/server.py`
- Test:   `phase1-pablo/tests/test_runs_api.py`

Responsibility: return newest-first list of runs whose status is terminal (`done`/`cancelled`/`failed`), including `artifact_count`.

- [ ] **Step 1: Write the failing test**

`phase1-pablo/tests/test_runs_api.py`:

```python
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient


@pytest_asyncio.fixture
async def seeded_runs(monkeypatch):
    """Seed three runs through the real DatabaseService used by the app."""
    import shared
    from shared.models import Run

    await shared.init()
    now = datetime.utcnow()
    ids = [uuid.uuid4() for _ in range(4)]
    async with shared.db.get_session() as s:
        s.add_all(
            [
                Run(id=ids[0], problem_description="p-done", status="done",
                    s3_prefix=f"research/{ids[0]}", artifact_count=3,
                    created_at=now - timedelta(minutes=3)),
                Run(id=ids[1], problem_description="p-cancel", status="cancelled",
                    s3_prefix=f"research/{ids[1]}", artifact_count=None,
                    created_at=now - timedelta(minutes=2)),
                Run(id=ids[2], problem_description="p-fail", status="failed",
                    s3_prefix=f"research/{ids[2]}", artifact_count=None,
                    created_at=now - timedelta(minutes=1)),
                Run(id=ids[3], problem_description="p-running", status="running",
                    s3_prefix=f"research/{ids[3]}", created_at=now),
            ]
        )
        await s.commit()
    yield [str(i) for i in ids]
    async with shared.db.get_session() as s:
        for rid in ids:
            await s.execute(
                __import__("sqlalchemy").delete(Run).where(Run.id == rid)
            )
        await s.commit()
    await shared.shutdown()


@pytest.mark.asyncio
async def test_runs_list_excludes_running_and_orders_newest_first(seeded_runs):
    from decisionlab.server import app

    with TestClient(app) as client:
        resp = client.get("/api/runs")
    assert resp.status_code == 200
    payload = resp.json()
    statuses = [r["status"] for r in payload]
    # running is filtered out
    assert "running" not in statuses
    # newest first (failed was created last among the three terminal ones)
    assert statuses[:3] == ["failed", "cancelled", "done"]
    # fields present
    sample = payload[0]
    assert set(sample.keys()) == {
        "run_id", "problem", "status", "started_at", "artifact_count",
    }
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd phase1-pablo && uv run pytest tests/test_runs_api.py -v
```

Expected: FAIL — endpoint missing or returns 404.

- [ ] **Step 3: Implement the endpoint in `server.py`**

Append after the existing `kg_snapshot` endpoint:

```python
@app.get("/api/runs")
async def list_runs() -> list[dict]:
    """Return terminal runs newest-first for the idle-screen past-runs list."""
    import shared
    from shared.models import Run
    from sqlalchemy import select

    async with shared.db.get_session() as session:
        stmt = (
            select(Run)
            .where(Run.status.in_(["done", "cancelled", "failed"]))
            .order_by(Run.created_at.desc())
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [
        {
            "run_id": str(r.id),
            "problem": r.problem_description,
            "status": r.status,
            "started_at": r.created_at.isoformat() + "Z",
            "artifact_count": r.artifact_count,
        }
        for r in rows
    ]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd phase1-pablo && uv run pytest tests/test_runs_api.py -v
```

Expected: 1 PASSED.

- [ ] **Step 5: Commit**

```bash
cd phase1-pablo
git add src/decisionlab/server.py tests/test_runs_api.py
git commit -m "feat[decisionlab]: GET /api/runs lists terminal runs newest-first"
```

---

## Task 8: `GET /api/runs/{run_id}/events` endpoint

**Files:**
- Modify: `phase1-pablo/src/decisionlab/server.py`
- Test:   `phase1-pablo/tests/test_runs_api.py` (append)

Responsibility: stream the recorded NDJSON for a run. 404 if absent, 409 if the run is still running.

- [ ] **Step 1: Append the failing test**

Add to `phase1-pablo/tests/test_runs_api.py`:

```python
@pytest.mark.asyncio
async def test_events_endpoint_returns_ndjson(seeded_runs):
    import shared
    from decisionlab.server import app

    run_id = seeded_runs[0]  # the 'done' run
    await shared.storage.put_text(
        f"research/{run_id}/events.jsonl",
        '{"seq":1,"type":"run_start"}\n{"seq":2,"type":"pipeline_done"}\n',
        content_type="application/x-ndjson",
    )
    try:
        with TestClient(app) as client:
            resp = client.get(f"/api/runs/{run_id}/events")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/x-ndjson")
        lines = resp.text.strip().split("\n")
        assert len(lines) == 2
    finally:
        await shared.storage.delete(f"research/{run_id}/events.jsonl")


@pytest.mark.asyncio
async def test_events_endpoint_returns_404_when_missing(seeded_runs):
    from decisionlab.server import app

    run_id = seeded_runs[0]
    with TestClient(app) as client:
        resp = client.get(f"/api/runs/{run_id}/events")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_events_endpoint_returns_409_while_running(seeded_runs):
    from decisionlab.server import app

    run_id = seeded_runs[3]  # the 'running' one
    with TestClient(app) as client:
        resp = client.get(f"/api/runs/{run_id}/events")
    assert resp.status_code == 409
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd phase1-pablo && uv run pytest tests/test_runs_api.py -v
```

Expected: the 3 new tests FAIL.

- [ ] **Step 3: Implement the endpoint in `server.py`**

Append after `list_runs`:

```python
@app.get("/api/runs/{run_id}/events")
async def get_run_events(run_id: str):
    """Stream the recorded WS event stream for a run (NDJSON)."""
    import shared
    from shared.models import Run
    from sqlalchemy import select
    from fastapi.responses import PlainTextResponse

    async with shared.db.get_session() as session:
        result = await session.execute(
            select(Run.status).where(Run.id == uuid.UUID(run_id))
        )
        row = result.first()
    if row is not None and row[0] == "running":
        raise HTTPException(status_code=409, detail="Run still in progress")

    key = f"research/{run_id}/events.jsonl"
    if not await shared.storage.exists(key):
        raise HTTPException(status_code=404, detail="Event log not found")
    body = await shared.storage.get_text(key)
    return PlainTextResponse(body, media_type="application/x-ndjson")
```

Make sure `import uuid` is present at the top of `server.py` (it already is — used in `run_pipeline`).

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd phase1-pablo && uv run pytest tests/test_runs_api.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
cd phase1-pablo
git add src/decisionlab/server.py tests/test_runs_api.py
git commit -m "feat[decisionlab]: GET /api/runs/:id/events streams recorded NDJSON"
```

---

## Task 9: Frontend types — `RecordedEvent`, `review_decision`, `ReplayMode`

**Files:**
- Modify: `phase1-pablo/web/src/types.ts`

Responsibility: widen the `ServerMessage` union; add supporting types for the replay engine.

- [ ] **Step 1: Edit `types.ts`**

Add, directly below the existing `ServerMessage` union (around line 71), a new line before the closing `;`:

```ts
  | { type: "review_decision"; stage: Stage; approved: Record<string, boolean> | unknown };
```

Then, at the bottom of the file (after `TOOL_ICONS`), append:

```ts
// Replay engine types
export interface RecordedEvent {
  seq?: number;
  ts: number;
  [key: string]: unknown;
}

export type ReplayMode = "idle" | "live" | "live-finished" | "replay";

export interface PastRun {
  run_id: string;
  problem: string;
  status: "done" | "cancelled" | "failed";
  started_at: string;
  artifact_count: number | null;
}
```

- [ ] **Step 2: Type-check the web project**

```bash
cd phase1-pablo/web && pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd phase1-pablo/web
git add src/types.ts
git commit -m "feat[web]: replay engine types (RecordedEvent, ReplayMode, PastRun)"
```

---

## Task 10: `deriveGraphState` — pure reducer fold

**Files:**
- Create: `phase1-pablo/web/src/lib/deriveGraphState.ts`
- Create: `phase1-pablo/web/src/lib/deriveGraphState.test.ts`

Responsibility: given an event slice, produce the same `{nodes, edges, stages, currentStage, agents}` the live reducer would produce.

- [ ] **Step 1: Install vitest if not present**

```bash
cd phase1-pablo/web && pnpm ls vitest
```

If vitest is not listed, install:

```bash
cd phase1-pablo/web && pnpm add -D vitest @vitest/ui
```

Add the `test` script to `package.json` (if not present) under `"scripts"`:

```json
    "test": "vitest run",
    "test:watch": "vitest"
```

- [ ] **Step 2: Write the failing test**

`phase1-pablo/web/src/lib/deriveGraphState.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { deriveGraphState } from "./deriveGraphState";
import { Stage } from "../types";

const nodeA = {
  id: "a",
  kind: "agent" as const,
  label: "researcher",
  status: "running" as const,
  meta: {},
};

describe("deriveGraphState", () => {
  it("folds node_add, stage_change, node_update", () => {
    const events = [
      { ts: 1, type: "run_start", run_id: "r1" },
      { ts: 2, type: "stage_change", stage: Stage.RESEARCH, status: "running" },
      { ts: 3, type: "node_add", node: nodeA },
      { ts: 4, type: "node_update", id: "a", status: "done" },
    ];
    const state = deriveGraphState(events);
    expect(state.currentStage).toBe(Stage.RESEARCH);
    expect(state.nodes).toHaveLength(1);
    expect(state.nodes[0].status).toBe("done");
  });

  it("is deterministic — same inputs give same output", () => {
    const events = [
      { ts: 1, type: "node_add", node: nodeA },
      { ts: 2, type: "edge_add", edge: { source: "a", target: "b" } },
    ];
    expect(deriveGraphState(events)).toEqual(deriveGraphState(events));
  });

  it("folds a partial prefix", () => {
    const events = [
      { ts: 1, type: "node_add", node: nodeA },
      { ts: 2, type: "node_update", id: "a", status: "done" },
    ];
    const partial = deriveGraphState(events.slice(0, 1));
    expect(partial.nodes[0].status).toBe("running");
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd phase1-pablo/web && pnpm test src/lib/deriveGraphState.test.ts
```

Expected: FAIL — `Cannot find module './deriveGraphState'`.

- [ ] **Step 4: Implement `deriveGraphState.ts`**

`phase1-pablo/web/src/lib/deriveGraphState.ts`:

```ts
import type { GraphNode, GraphEdge, Stage, StageStatus, AgentState } from "../types";

export interface DerivedGraphState {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stages: Record<Stage, StageStatus>;
  currentStage: Stage | null;
  agents: AgentState[];
  approvals: Record<string, boolean>;
}

function emptyStages(): Record<Stage, StageStatus> {
  return {} as Record<Stage, StageStatus>;
}

function emptyState(): DerivedGraphState {
  return {
    nodes: [],
    edges: [],
    stages: emptyStages(),
    currentStage: null,
    agents: [],
    approvals: {},
  };
}

function stepOne(state: DerivedGraphState, ev: Record<string, any>): DerivedGraphState {
  switch (ev.type) {
    case "stage_change":
      return {
        ...state,
        stages: { ...state.stages, [ev.stage]: ev.status },
        currentStage: ev.status === "running" ? ev.stage : state.currentStage,
      };
    case "node_add":
      return { ...state, nodes: [...state.nodes, ev.node] };
    case "edge_add":
      return { ...state, edges: [...state.edges, ev.edge] };
    case "node_update":
      return {
        ...state,
        nodes: state.nodes.map((n) => (n.id === ev.id ? { ...n, status: ev.status } : n)),
      };
    case "graph_clear":
      return { ...state, nodes: [], edges: [] };
    case "agents":
      return {
        ...state,
        agents: ev.agents.map((a: any) => ({ name: a.name, color: a.color, status: "idle" as const })),
      };
    case "agent_status":
      return {
        ...state,
        agents: state.agents.map((a) => (a.name === ev.agent ? { ...a, status: ev.status } : a)),
      };
    case "review_decision": {
      if (ev.approved && typeof ev.approved === "object") {
        return { ...state, approvals: { ...state.approvals, ...(ev.approved as Record<string, boolean>) } };
      }
      return state;
    }
    default:
      return state;
  }
}

export function deriveGraphState(events: readonly Record<string, any>[]): DerivedGraphState {
  let state = emptyState();
  for (const ev of events) state = stepOne(state, ev);
  return state;
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd phase1-pablo/web && pnpm test src/lib/deriveGraphState.test.ts
```

Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
cd phase1-pablo/web
git add src/lib/deriveGraphState.ts src/lib/deriveGraphState.test.ts package.json pnpm-lock.yaml
git commit -m "feat[web]: deriveGraphState pure fold used by both live and replay"
```

---

## Task 11: `stageMarkers` and `reviewMarkers`

**Files:**
- Create: `phase1-pablo/web/src/lib/markers.ts`
- Create: `phase1-pablo/web/src/lib/markers.test.ts`

Responsibility: extract stage and review positions from an event array for the timeline scrubber.

- [ ] **Step 1: Write the failing test**

`phase1-pablo/web/src/lib/markers.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { extractMarkers } from "./markers";
import { Stage } from "../types";

describe("extractMarkers", () => {
  it("captures each running stage_change as a marker", () => {
    const events = [
      { ts: 1, type: "run_start" },
      { ts: 2, type: "stage_change", stage: Stage.RESEARCH, status: "running" },
      { ts: 3, type: "node_add", node: {} },
      { ts: 4, type: "stage_change", stage: Stage.REVIEW_RESEARCH, status: "running" },
      { ts: 5, type: "stage_change", stage: Stage.FORMALIZE, status: "running" },
    ];
    const { stageMarkers } = extractMarkers(events);
    expect(stageMarkers.map((m) => m.cursor)).toEqual([1, 3, 4]);
    expect(stageMarkers.map((m) => m.stage)).toEqual([
      Stage.RESEARCH,
      Stage.REVIEW_RESEARCH,
      Stage.FORMALIZE,
    ]);
  });

  it("pairs review_request with review_decision when present", () => {
    const events = [
      { ts: 1, type: "review_request", stage: Stage.REVIEW_RESEARCH },
      { ts: 2, type: "review_decision", stage: Stage.REVIEW_RESEARCH, approved: { a: true } },
      { ts: 3, type: "review_request", stage: Stage.REVIEW_FORMALIZE },
    ];
    const { reviewMarkers } = extractMarkers(events);
    expect(reviewMarkers).toEqual([
      { cursor: 0, stage: Stage.REVIEW_RESEARCH, approved: true },
      { cursor: 2, stage: Stage.REVIEW_FORMALIZE, approved: null },
    ]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd phase1-pablo/web && pnpm test src/lib/markers.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement `markers.ts`**

`phase1-pablo/web/src/lib/markers.ts`:

```ts
import type { Stage } from "../types";

export interface StageMarker {
  cursor: number;
  stage: Stage;
}

export interface ReviewMarker {
  cursor: number;
  stage: Stage;
  approved: boolean | null; // null = decision absent (incomplete run)
}

export function extractMarkers(events: readonly Record<string, any>[]): {
  stageMarkers: StageMarker[];
  reviewMarkers: ReviewMarker[];
} {
  const stageMarkers: StageMarker[] = [];
  const reviewMarkers: ReviewMarker[] = [];
  const pendingReview: { index: number; stage: Stage }[] = [];

  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    if (ev.type === "stage_change" && ev.status === "running") {
      stageMarkers.push({ cursor: i, stage: ev.stage });
    } else if (ev.type === "review_request") {
      pendingReview.push({ index: i, stage: ev.stage });
    } else if (ev.type === "review_decision") {
      const match = pendingReview.pop();
      const approved = isAllApproved(ev.approved);
      reviewMarkers.push({
        cursor: match ? match.index : i,
        stage: ev.stage,
        approved,
      });
    }
  }
  for (const { index, stage } of pendingReview) {
    reviewMarkers.push({ cursor: index, stage, approved: null });
  }
  reviewMarkers.sort((a, b) => a.cursor - b.cursor);
  return { stageMarkers, reviewMarkers };
}

function isAllApproved(approved: unknown): boolean | null {
  if (!approved || typeof approved !== "object") return null;
  const vals = Object.values(approved as Record<string, unknown>);
  if (vals.length === 0) return null;
  if (vals.every((v) => v === true)) return true;
  if (vals.every((v) => v === false)) return false;
  return null; // mixed
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd phase1-pablo/web && pnpm test src/lib/markers.test.ts
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
cd phase1-pablo/web
git add src/lib/markers.ts src/lib/markers.test.ts
git commit -m "feat[web]: extract stage and review markers for replay timeline"
```

---

## Task 12: `groupBoundaries` — agent-action step granularity

**Files:**
- Create: `phase1-pablo/web/src/lib/groupBoundaries.ts`
- Create: `phase1-pablo/web/src/lib/groupBoundaries.test.ts`

Responsibility: compute the indices that separate "one agent action" groups for step-forward/back.

- [ ] **Step 1: Write the failing test**

`phase1-pablo/web/src/lib/groupBoundaries.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { groupBoundaries } from "./groupBoundaries";

describe("groupBoundaries", () => {
  it("splits on agent_status idle and on stage_change", () => {
    const events = [
      { ts: 1, type: "agent_status", agent: "researcher", status: "working" }, // 0
      { ts: 2, type: "node_add", node: {} },                                    // 1
      { ts: 3, type: "agent_status", agent: "researcher", status: "idle" },     // 2 — boundary at 3
      { ts: 4, type: "stage_change", stage: "formalize", status: "running" },   // 3 — boundary at 4
      { ts: 5, type: "node_add", node: {} },                                    // 4
    ];
    // Boundaries are cursor positions after which a group ends (1..N).
    expect(groupBoundaries(events)).toEqual([3, 4, 5]);
  });

  it("handles an empty stream", () => {
    expect(groupBoundaries([])).toEqual([]);
  });

  it("emits a final boundary at events.length", () => {
    const events = [{ ts: 1, type: "node_add", node: {} }];
    expect(groupBoundaries(events)).toEqual([1]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd phase1-pablo/web && pnpm test src/lib/groupBoundaries.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement `groupBoundaries.ts`**

`phase1-pablo/web/src/lib/groupBoundaries.ts`:

```ts
/**
 * Compute cursor positions (1..events.length) that end an "agent action" group.
 * A group ends when either:
 *   - an agent_status event transitions an agent to "idle", OR
 *   - a stage_change event fires.
 * The final cursor position is always included so stepForward from the last
 * group lands at the end of the stream.
 */
export function groupBoundaries(events: readonly Record<string, any>[]): number[] {
  const out: number[] = [];
  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    const ends =
      (ev.type === "agent_status" && ev.status === "idle") ||
      ev.type === "stage_change";
    if (ends) out.push(i + 1);
  }
  if (events.length > 0 && (out.length === 0 || out[out.length - 1] !== events.length)) {
    out.push(events.length);
  }
  return out;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd phase1-pablo/web && pnpm test src/lib/groupBoundaries.test.ts
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
cd phase1-pablo/web
git add src/lib/groupBoundaries.ts src/lib/groupBoundaries.test.ts
git commit -m "feat[web]: group boundaries for agent-action step granularity"
```

---

## Task 13: `useReplay` hook — load, seek, stepForward/Back

**Files:**
- Create: `phase1-pablo/web/src/hooks/useReplay.ts`
- Create: `phase1-pablo/web/src/hooks/useReplay.test.ts`

Responsibility: own `events`, `cursor`, and navigation actions. Playback loop lives in the next task.

- [ ] **Step 1: Write the failing test**

`phase1-pablo/web/src/hooks/useReplay.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useReplay } from "./useReplay";

const sampleEvents = [
  { ts: 1000, type: "run_start", run_id: "r1" },
  { ts: 1100, type: "stage_change", stage: "research", status: "running" },
  { ts: 1200, type: "node_add", node: { id: "a", kind: "agent", label: "x", status: "running", meta: {} } },
  { ts: 1300, type: "agent_status", agent: "researcher", status: "idle" },
  { ts: 1400, type: "stage_change", stage: "formalize", status: "running" },
];

describe("useReplay", () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url: string) => ({
      ok: true,
      text: async () => sampleEvents.map((e) => JSON.stringify(e)).join("\n"),
    })) as any;
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads events and starts at cursor=events.length in replay mode", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => {
      await result.current.load("r1");
    });
    expect(result.current.events).toHaveLength(5);
    expect(result.current.cursor).toBe(5);
    expect(result.current.mode).toBe("replay");
  });

  it("seeks to a cursor clamped to bounds", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    act(() => result.current.seek(-10));
    expect(result.current.cursor).toBe(0);
    act(() => result.current.seek(999));
    expect(result.current.cursor).toBe(5);
    act(() => result.current.seek(2));
    expect(result.current.cursor).toBe(2);
  });

  it("stepForward advances to the next group boundary", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    act(() => result.current.seek(0));
    act(() => result.current.stepForward());
    // idle at index 3 → boundary 4
    expect(result.current.cursor).toBe(4);
    act(() => result.current.stepForward());
    // stage_change at index 4 → boundary 5
    expect(result.current.cursor).toBe(5);
  });

  it("stepBack retreats to the previous boundary", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    // cursor starts at 5
    act(() => result.current.stepBack());
    expect(result.current.cursor).toBe(4);
    act(() => result.current.stepBack());
    expect(result.current.cursor).toBe(0);
  });
});
```

- [ ] **Step 2: Install testing-library if needed**

```bash
cd phase1-pablo/web && pnpm ls @testing-library/react
```

If missing:

```bash
cd phase1-pablo/web && pnpm add -D @testing-library/react jsdom
```

Add to `vite.config.ts` (create a separate `vitest.config.ts` if preferred; keeping it minimal here) inside `defineConfig({ ... })`:

```ts
  test: {
    environment: "jsdom",
    globals: true,
  },
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd phase1-pablo/web && pnpm test src/hooks/useReplay.test.ts
```

Expected: FAIL — hook missing.

- [ ] **Step 4: Implement `useReplay.ts`**

`phase1-pablo/web/src/hooks/useReplay.ts`:

```ts
import { useCallback, useMemo, useRef, useState } from "react";
import type { RecordedEvent, ReplayMode, Stage } from "../types";
import { extractMarkers, type StageMarker, type ReviewMarker } from "../lib/markers";
import { groupBoundaries } from "../lib/groupBoundaries";

export interface UseReplay {
  events: RecordedEvent[];
  cursor: number;
  playing: boolean;
  speed: 1 | 2 | 4;
  mode: ReplayMode;
  stageMarkers: StageMarker[];
  reviewMarkers: ReviewMarker[];
  load(runId: string): Promise<void>;
  seek(cursor: number): void;
  stepForward(): void;
  stepBack(): void;
  prevStage(): void;
  nextStage(): void;
  goLive(): void;
  setSpeed(s: 1 | 2 | 4): void;
  play(): void;
  pause(): void;
  appendLive(event: RecordedEvent): void;
  setMode(m: ReplayMode): void;
}

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

export function useReplay(): UseReplay {
  const [events, setEvents] = useState<RecordedEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<1 | 2 | 4>(1);
  const [mode, setMode] = useState<ReplayMode>("idle");
  const playTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { stageMarkers, reviewMarkers } = useMemo(() => extractMarkers(events), [events]);
  const boundaries = useMemo(() => groupBoundaries(events), [events]);

  const clear = () => {
    if (playTimerRef.current) {
      clearTimeout(playTimerRef.current);
      playTimerRef.current = null;
    }
    setPlaying(false);
  };

  const load = useCallback(async (runId: string) => {
    clear();
    const resp = await fetch(`/api/runs/${runId}/events`);
    if (!resp.ok) throw new Error(`Failed to load run ${runId}`);
    const text = await resp.text();
    const parsed: RecordedEvent[] = text
      .split("\n")
      .filter((ln) => ln.trim())
      .map((ln) => JSON.parse(ln));
    setEvents(parsed);
    setCursor(parsed.length);
    setMode("replay");
  }, []);

  const seek = useCallback((c: number) => {
    clear();
    setCursor((prev) => clamp(c, 0, eventsRef.current.length));
  }, []);

  // events-ref lets callbacks see the current length without re-creating on every event append
  const eventsRef = useRef(events);
  eventsRef.current = events;
  const boundariesRef = useRef(boundaries);
  boundariesRef.current = boundaries;

  const stepForward = useCallback(() => {
    clear();
    setCursor((prev) => {
      const next = boundariesRef.current.find((b) => b > prev);
      return next ?? eventsRef.current.length;
    });
  }, []);

  const stepBack = useCallback(() => {
    clear();
    setCursor((prev) => {
      const prevBoundaries = boundariesRef.current.filter((b) => b < prev);
      return prevBoundaries.length ? prevBoundaries[prevBoundaries.length - 1] : 0;
    });
  }, []);

  const stageMarkersRef = useRef(stageMarkers);
  stageMarkersRef.current = stageMarkers;

  const prevStage = useCallback(() => {
    clear();
    setCursor((prev) => {
      const earlier = stageMarkersRef.current.filter((m) => m.cursor < prev);
      return earlier.length ? earlier[earlier.length - 1].cursor : 0;
    });
  }, []);

  const nextStage = useCallback(() => {
    clear();
    setCursor((prev) => {
      const later = stageMarkersRef.current.find((m) => m.cursor > prev);
      return later ? later.cursor : eventsRef.current.length;
    });
  }, []);

  const goLive = useCallback(() => {
    clear();
    setCursor(eventsRef.current.length);
  }, []);

  const play = useCallback(() => setPlaying(true), []);
  const pause = useCallback(() => {
    clear();
  }, []);

  const appendLive = useCallback((event: RecordedEvent) => {
    setEvents((prev) => [...prev, event]);
  }, []);

  return {
    events,
    cursor,
    playing,
    speed,
    mode,
    stageMarkers,
    reviewMarkers,
    load,
    seek,
    stepForward,
    stepBack,
    prevStage,
    nextStage,
    goLive,
    setSpeed,
    play,
    pause,
    appendLive,
    setMode,
  };
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd phase1-pablo/web && pnpm test src/hooks/useReplay.test.ts
```

Expected: 4 PASSED.

- [ ] **Step 6: Commit**

```bash
cd phase1-pablo/web
git add src/hooks/useReplay.ts src/hooks/useReplay.test.ts vite.config.ts package.json pnpm-lock.yaml
git commit -m "feat[web]: useReplay hook — load/seek/step navigation"
```

---

## Task 14: `useReplay` — playback loop (play/pause/speed + 300 ms cap)

**Files:**
- Modify: `phase1-pablo/web/src/hooks/useReplay.ts`
- Modify: `phase1-pablo/web/src/hooks/useReplay.test.ts` (append)

Responsibility: when `playing === true`, advance the cursor by 1 every `(next.ts - curr.ts)/speed` ms, capped at 300 ms. Stop at `events.length`.

- [ ] **Step 1: Append the failing test**

Append to `phase1-pablo/web/src/hooks/useReplay.test.ts`:

```ts
describe("useReplay playback", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    global.fetch = vi.fn(async () => ({
      ok: true,
      text: async () => [
        { ts: 0,   type: "run_start" },
        { ts: 100, type: "node_add", node: {} },
        { ts: 250, type: "node_add", node: {} },
      ].map((e) => JSON.stringify(e)).join("\n"),
    })) as any;
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("advances the cursor at real inter-event timings when playing", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    act(() => result.current.seek(0));
    act(() => result.current.play());

    // first gap = 100ms
    await act(async () => { vi.advanceTimersByTime(100); });
    expect(result.current.cursor).toBe(1);

    // second gap = 150ms
    await act(async () => { vi.advanceTimersByTime(150); });
    expect(result.current.cursor).toBe(2);

    // third advance (last event → stop), pending timeout fires and stops playback
    await act(async () => { vi.advanceTimersByTime(1000); });
    expect(result.current.cursor).toBe(3);
    expect(result.current.playing).toBe(false);
  });

  it("caps inter-event delay at 300ms", async () => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      text: async () => [
        { ts: 0,    type: "run_start" },
        { ts: 5000, type: "node_add", node: {} },
      ].map((e) => JSON.stringify(e)).join("\n"),
    })) as any;

    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    act(() => result.current.seek(0));
    act(() => result.current.play());
    await act(async () => { vi.advanceTimersByTime(300); });
    expect(result.current.cursor).toBe(1);
  });

  it("speed=2 halves the delay", async () => {
    const { result } = renderHook(() => useReplay());
    await act(async () => { await result.current.load("r1"); });
    act(() => result.current.seek(0));
    act(() => result.current.setSpeed(2));
    act(() => result.current.play());
    await act(async () => { vi.advanceTimersByTime(50); });
    expect(result.current.cursor).toBe(1); // 100/2 = 50ms
  });
});
```

- [ ] **Step 2: Run to verify failure**

```bash
cd phase1-pablo/web && pnpm test src/hooks/useReplay.test.ts
```

Expected: the three new cases FAIL (no playback loop yet).

- [ ] **Step 3: Add the playback loop**

At the end of `useReplay.ts` before the `return`, add:

```ts
  // ---- playback loop ----
  const speedRef = useRef<1 | 2 | 4>(speed);
  speedRef.current = speed;

  const schedule = useCallback((currentCursor: number) => {
    if (playTimerRef.current) clearTimeout(playTimerRef.current);
    if (currentCursor >= eventsRef.current.length - 1) {
      setPlaying(false);
      return;
    }
    const a = eventsRef.current[currentCursor];
    const b = eventsRef.current[currentCursor + 1];
    const rawDelay = Math.max(0, (b.ts as number) - (a.ts as number));
    const delay = Math.min(300, rawDelay) / speedRef.current;
    playTimerRef.current = setTimeout(() => {
      setCursor((prev) => {
        const next = prev + 1;
        if (next >= eventsRef.current.length) {
          setPlaying(false);
          return eventsRef.current.length;
        }
        schedule(next);
        return next;
      });
    }, delay);
  }, []);

  // when `playing` flips to true, start the loop from the current cursor
  useMemo(() => {
    if (playing) schedule(cursor);
    return null;
  }, [playing]); // intentionally not depending on cursor — only (re)start on play
```

(This uses `useMemo` purely for its effect-timing without re-running every cursor change; alternatively use `useEffect` — both work. Pick `useEffect` if lint complains.)

- [ ] **Step 4: Run tests to verify passing**

```bash
cd phase1-pablo/web && pnpm test src/hooks/useReplay.test.ts
```

Expected: 7 PASSED (4 from Task 13 + 3 new).

- [ ] **Step 5: Commit**

```bash
cd phase1-pablo/web
git add src/hooks/useReplay.ts src/hooks/useReplay.test.ts
git commit -m "feat[web]: replay playback loop with real timing and 300ms cap"
```

---

## Task 15: `<PastRunsList />` component

**Files:**
- Create: `phase1-pablo/web/src/components/PastRunsList.tsx`

Responsibility: fetch `/api/runs`, render the list as shown in the spec, fire `onSelect(runId)` on click. Absolutely positioned at the left of the idle input bar so the textarea stays centred.

- [ ] **Step 1: Create the component**

`phase1-pablo/web/src/components/PastRunsList.tsx`:

```tsx
import { useEffect, useState } from "react";
import type { PastRun } from "../types";

function statusPillClass(status: PastRun["status"]): string {
  const base =
    "text-[9px] uppercase tracking-[1px] px-2 py-0.5 rounded-full border";
  if (status === "done") return `${base} border-border text-text-muted`;
  if (status === "failed") return `${base} border-border text-accent-red`;
  return `${base} border-border text-text-dim`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

interface Props {
  onSelect: (runId: string) => void;
}

export default function PastRunsList({ onSelect }: Props) {
  const [runs, setRuns] = useState<PastRun[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/api/runs");
        if (!r.ok) throw new Error("failed");
        const data: PastRun[] = await r.json();
        if (!cancelled) setRuns(data);
      } catch {
        if (!cancelled) setRuns([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (runs === null || runs.length === 0) return null;

  return (
    <div className="absolute left-6 bottom-5 w-[260px] max-h-[180px] overflow-y-auto bg-surface/80 backdrop-blur-xl border border-border rounded-xl shadow-xl shadow-black/20 p-2">
      <div className="text-[10px] uppercase tracking-[1.5px] text-text-faint px-2 py-1">
        Past runs
      </div>
      {runs.map((r) => (
        <button
          key={r.run_id}
          onClick={() => onSelect(r.run_id)}
          className="w-full text-left px-2 py-2 rounded-lg hover:bg-surface-hover border-none bg-transparent cursor-pointer"
        >
          <div className="text-[12px] text-text truncate">{r.problem}</div>
          <div className="flex items-center gap-2 mt-1">
            <span className={statusPillClass(r.status)}>{r.status}</span>
            {r.artifact_count !== null && (
              <span className="text-[10px] text-text-muted">
                {r.artifact_count} model{r.artifact_count === 1 ? "" : "s"}
              </span>
            )}
            <span className="text-[10px] text-text-dim ml-auto">
              {formatDate(r.started_at)}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd phase1-pablo/web && pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd phase1-pablo/web
git add src/components/PastRunsList.tsx
git commit -m "feat[web]: PastRunsList component for idle screen"
```

---

## Task 16: `<Timeline />` component (expanded + collapsed)

**Files:**
- Create: `phase1-pablo/web/src/components/Timeline.tsx`

Responsibility: floating pill at bottom centre, collapse/expand, fires replay-hook actions. No tests at this stage — visual component, covered by the Playwright E2E pass.

- [ ] **Step 1: Create the component**

`phase1-pablo/web/src/components/Timeline.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import {
  SkipBack,
  SkipForward,
  Play,
  Pause,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Radio,
  X,
} from "lucide-react";
import type { UseReplay } from "../hooks/useReplay";

const LS_KEY = "decisionlab.timeline.collapsed";

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

interface Props {
  replay: UseReplay;
  onExit?: () => void; // only meaningful in "replay" mode
  reviewActive: boolean; // auto-collapse hint
}

export default function Timeline({ replay, onExit, reviewActive }: Props) {
  const {
    events,
    cursor,
    playing,
    speed,
    mode,
    stageMarkers,
    reviewMarkers,
    play,
    pause,
    seek,
    stepForward,
    stepBack,
    prevStage,
    nextStage,
    goLive,
    setSpeed,
  } = replay;

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(LS_KEY) === "1";
    } catch {
      return false;
    }
  });

  // auto-collapse when a review bar is active
  useEffect(() => {
    if (reviewActive) setCollapsed(true);
  }, [reviewActive]);

  useEffect(() => {
    try {
      localStorage.setItem(LS_KEY, collapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  const total = events.length;
  const elapsed = useMemo(() => {
    if (total === 0) return 0;
    const first = events[0].ts as number;
    const idx = Math.max(0, Math.min(cursor, total) - 1);
    return (events[idx].ts as number) - first;
  }, [cursor, total, events]);
  const duration = useMemo(() => {
    if (total < 2) return 0;
    return (events[total - 1].ts as number) - (events[0].ts as number);
  }, [events, total]);

  if (mode === "idle") return null;

  if (collapsed) {
    return (
      <div className="absolute left-1/2 bottom-4 -translate-x-1/2 z-30 flex items-center gap-2 bg-surface/80 backdrop-blur-xl border border-border rounded-full shadow-xl shadow-black/30 px-3 py-2">
        <button
          className="w-7 h-7 flex items-center justify-center rounded-full bg-transparent border-none text-text cursor-pointer hover:bg-surface-hover"
          onClick={playing ? pause : play}
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}
        </button>
        <span className="text-[11px] text-text-muted font-mono">
          {formatElapsed(elapsed)}
        </span>
        <button
          className="w-7 h-7 flex items-center justify-center rounded-full bg-transparent border-none text-text-faint cursor-pointer hover:bg-surface-hover"
          onClick={() => setCollapsed(false)}
          aria-label="Expand timeline"
        >
          <ChevronUp size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="absolute left-1/2 bottom-4 -translate-x-1/2 z-30 w-[720px] bg-surface/80 backdrop-blur-xl border border-border rounded-2xl shadow-xl shadow-black/30 px-4 py-3">
      <div className="flex items-center gap-2">
        <button className="tl-btn" onClick={prevStage} aria-label="Previous stage">
          <SkipBack size={14} />
        </button>
        <button className="tl-btn" onClick={stepBack} aria-label="Step back">
          <ChevronLeft size={14} />
        </button>
        <button
          className="tl-btn tl-btn-primary"
          onClick={playing ? pause : play}
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}
        </button>
        <button className="tl-btn" onClick={stepForward} aria-label="Step forward">
          <ChevronRight size={14} />
        </button>
        <button className="tl-btn" onClick={nextStage} aria-label="Next stage">
          <SkipForward size={14} />
        </button>

        <div className="flex-1 relative h-4 mx-2">
          <div className="absolute inset-0 top-1/2 -translate-y-1/2 h-[2px] bg-border" />
          <div
            className="absolute top-1/2 -translate-y-1/2 h-[2px] bg-text-muted"
            style={{ width: total ? `${(cursor / total) * 100}%` : "0%" }}
          />
          {stageMarkers.map((m, i) => (
            <div
              key={`sm-${i}`}
              title={m.stage}
              className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-text-muted cursor-pointer"
              style={{ left: `calc(${(m.cursor / total) * 100}% - 4px)` }}
              onClick={() => seek(m.cursor)}
            />
          ))}
          {reviewMarkers.map((m, i) => (
            <div
              key={`rm-${i}`}
              title={`Review: ${m.stage} (${m.approved === true ? "approved" : m.approved === false ? "rejected" : "incomplete"})`}
              className="absolute top-1/2 -translate-y-1/2 w-1.5 h-3 rounded-sm bg-amber-400/80"
              style={{ left: `calc(${(m.cursor / total) * 100}% - 3px)` }}
            />
          ))}
          <input
            aria-label="Scrub"
            type="range"
            min={0}
            max={total}
            value={cursor}
            onChange={(e) => seek(parseInt(e.target.value))}
            className="absolute inset-0 w-full opacity-0 cursor-pointer"
          />
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rotate-45 bg-white"
            style={{ left: `calc(${(cursor / total) * 100}% - 6px)` }}
          />
        </div>

        <div className="flex gap-0.5 text-[11px] text-text-muted">
          {[1, 2, 4].map((s) => (
            <button
              key={s}
              onClick={() => setSpeed(s as 1 | 2 | 4)}
              className={`px-1.5 py-0.5 rounded ${speed === s ? "bg-surface-hover text-text" : ""}`}
            >
              {s}×
            </button>
          ))}
        </div>

        <span className="text-[11px] text-text-muted font-mono">
          {formatElapsed(elapsed)} / {formatElapsed(duration)}
        </span>

        <button
          className="tl-btn"
          onClick={goLive}
          aria-label={mode === "live" ? "Return to live" : "Jump to end"}
          title={mode === "live" ? "Return to live" : "Jump to end"}
        >
          <Radio size={14} />
        </button>

        <button
          className="tl-btn"
          onClick={() => setCollapsed(true)}
          aria-label="Collapse timeline"
        >
          <ChevronDown size={14} />
        </button>

        {mode === "replay" && onExit && (
          <button className="tl-btn" onClick={onExit} aria-label="Exit replay">
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
```

Add supporting utility classes to the global stylesheet. Append to `phase1-pablo/web/src/index.css`:

```css
@layer components {
  .tl-btn {
    @apply w-7 h-7 flex items-center justify-center rounded-full bg-transparent border-none text-text-muted cursor-pointer hover:bg-surface-hover;
  }
  .tl-btn-primary {
    @apply text-text;
  }
}
```

- [ ] **Step 2: Type-check**

```bash
cd phase1-pablo/web && pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd phase1-pablo/web
git add src/components/Timeline.tsx src/index.css
git commit -m "feat[web]: floating Timeline component for replay controls"
```

---

## Task 17: Live WS → `useReplay` integration + mode state machine

**Files:**
- Modify: `phase1-pablo/web/src/hooks/useWebSocket.ts`
- Modify: `phase1-pablo/web/src/App.tsx`

Responsibility: feed inbound WS events into the replay hook (so the live graph also runs through `deriveGraphState`); wire mode transitions.

- [ ] **Step 1: Expose the inbound-event callback from `useWebSocket`**

Modify `phase1-pablo/web/src/hooks/useWebSocket.ts`:

- Add a parameter `onServerMessage?: (msg: ServerMessage & {ts?: number}) => void` to the hook:

```ts
export function useWebSocket(
  onServerMessage?: (msg: ServerMessage) => void,
): WebSocketState & WebSocketActions {
```

- In the `ws.onmessage` handler, after dispatching, call the callback:

```ts
    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const msg: ServerMessage = JSON.parse(event.data);
        dispatch({ type: "SERVER_MSG", msg });
        onServerMessage?.(msg);
      } catch {
        console.error("[useWebSocket] Failed to parse message:", event.data);
      }
    };
```

- [ ] **Step 2: Wire `useReplay` into `App.tsx`**

At the top of `App.tsx`, after the existing imports, add:

```tsx
import Timeline from "./components/Timeline";
import PastRunsList from "./components/PastRunsList";
import { useReplay } from "./hooks/useReplay";
```

Inside `App`, above the existing `useWebSocket` call, declare:

```tsx
  const replay = useReplay();
```

Change the `useWebSocket(...)` call to pass an onServerMessage handler that feeds the replay hook's `appendLive` and flips the mode to live:

```tsx
  const {
    connected, nodes, edges, stages, currentStage, reviewRequest,
    isRunning, error, agents, runId,
    startPipeline, sendReviewResponse, sendRouterPrompt, cancelPipeline, clearError,
  } = useWebSocket((msg) => {
    // stamp with client-side ts so the replay engine can time-advance it
    replay.appendLive({ ts: Date.now(), ...(msg as any) });
    if (msg.type === "run_start") replay.setMode("live");
    if (msg.type === "pipeline_done") replay.setMode("live-finished");
  });
```

Add a mode-derived state and mode transitions:

```tsx
  const handleSelectPastRun = useCallback(
    async (runIdSel: string) => {
      if (isRunning) return; // blocked
      await replay.load(runIdSel);
    },
    [isRunning, replay],
  );
  const exitReplay = useCallback(() => {
    replay.setMode("idle");
  }, [replay]);
```

Replace the idle-block `<div className="absolute bottom-0 ...">` block's content so the textarea stays centred and the `PastRunsList` floats at the left. Specifically, inside the `showIdle` branch, after the existing `<DemoGraph ... />` line, add:

```tsx
              <PastRunsList onSelect={handleSelectPastRun} />
```

- [ ] **Step 3: Render the Timeline when not idle**

At the end of the JSX returned by `App` (after the `<KnowledgeGraphPanel ... />`), add:

```tsx
      {replay.mode !== "idle" && (
        <Timeline
          replay={replay}
          onExit={replay.mode === "replay" ? exitReplay : undefined}
          reviewActive={reviewActive}
        />
      )}
```

Also, reconcile `showIdle` so that entering replay switches out of idle. Change `showIdle`:

```tsx
  const hasGraph = nodes.length > 0 || replay.mode === "replay";
  const showIdle = !hasGraph && !isRunning && replay.mode === "idle";
```

And when the app is in `replay` mode, derive the graph from `replay.events.slice(0, replay.cursor)` instead of using `nodes/edges` from `useWebSocket`. Add a derivation:

```tsx
  const derived = useMemo(() => {
    if (replay.mode === "replay" || replay.mode === "live-finished") {
      // lazy import to avoid pulling in reducer during idle
      const { deriveGraphState } = require("./lib/deriveGraphState");
      return deriveGraphState(replay.events.slice(0, replay.cursor));
    }
    return null;
  }, [replay.mode, replay.events, replay.cursor]);

  const displayNodes = derived ? derived.nodes : nodes;
  const displayEdges = derived ? derived.edges : edges;
```

Then update the `<Graph ... />` usage to pass `displayNodes` and `displayEdges`:

```tsx
                <Graph
                  nodes={displayNodes}
                  edges={displayEdges}
                  onNodeClick={handleNodeClick}
                  reviewActive={reviewActive}
                  currentStage={currentStage}
                  dismissedOutputIds={dismissedOutputs}
                  outputApprovals={outputApprovals}
                  sidebarCollapsed={sidebarCollapsed}
                />
```

(If `require` upsets TS in ESM mode, replace with a top-level `import { deriveGraphState } from "./lib/deriveGraphState";`.)

- [ ] **Step 4: Type-check and run existing tests**

```bash
cd phase1-pablo/web && pnpm tsc --noEmit && pnpm test
```

Expected: no type errors; all existing vitest files pass.

- [ ] **Step 5: Commit**

```bash
cd phase1-pablo/web
git add src/hooks/useWebSocket.ts src/App.tsx
git commit -m "feat[web]: wire useReplay into App and switch Graph source by mode"
```

---

## Task 18: Playwright E2E manual verification

**Files:**
- (manual — no code changes)

Goal: validate the three user journeys in the spec §11 against the real UI.

- [ ] **Step 1: Boot the stack**

```bash
# Terminal 1
cd phase1-pablo && uv run uvicorn decisionlab.server:app --port 8000

# Terminal 2
cd phase1-pablo/web && pnpm dev
```

Open `http://localhost:5173/`.

- [ ] **Step 2: Past-run replay walk-through**

Run a full mock pipeline via the existing mock flow (use `scripts/run-mock.sh` if applicable), let it finish, then reload the page. Verify:
- Idle screen shows `<PastRunsList />` at the left.
- The just-finished run appears top of list with `done · N models`.
- Clicking the entry transitions out of idle; Graph is populated, Timeline appears.
- Scrubbing back reveals fewer nodes; scrubbing forward adds them back.
- Step forward lands one agent-action at a time.
- `Radio` (live/jump) button returns to end of the stream.
- `X` exits back to idle.

- [ ] **Step 3: In-run rewind at review**

Start a fresh live run. At the research review:
- Timeline is present (collapsed because the review bar is up).
- Expand with the chevron.
- Scrub back → graph rewinds into the running state; step forward replays the stage.
- Click `Radio` (live) → graph jumps to latest; approve the review via the existing review bar.

- [ ] **Step 4: Mode transition smoke**

- Idle → click past run → replay → click Exit → idle ✔
- Idle → type problem → Play → live → pipeline_done → live-finished → click past run → replay ✔
- During live, clicking a past-run item is blocked (confirm no navigation; no uncaught exceptions in console).

- [ ] **Step 5: Commit any small fixes you find**

If issues surface, fix and commit per `fix[web]: ...` or `fix[decisionlab]: ...`.

---

## Final validation

- [ ] **Run the entire backend test suite**

```bash
cd phase1-pablo && uv run pytest
```

Expected: no new failures relative to pre-feature baseline.

- [ ] **Run the entire frontend test suite**

```bash
cd phase1-pablo/web && pnpm test
```

Expected: all vitest files green.

- [ ] **Lint / format checks per project convention**

```bash
cd phase1-pablo && uv run ruff check . && uv run ruff format --check .
cd phase1-pablo/web && pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Push branch / open PR** (on user's request — do not push automatically).

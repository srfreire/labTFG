# Trace as the Canonical Replay Source — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `trace.jsonl` (the agrex Tracer artifact) the single source of truth for past-run visualization. Drop `events.jsonl` and the `EventLogger` plumbing entirely. Pipeline-level annotations (stage transitions, human-review prompts) ride on the tracer too via `tracer.stage()` and `tracer.marker()`, so the canonical artifact is also externally usable on https://agrex.ppazosp.dev with no additional layer.

**Architecture:** The Router already emits graph deltas via `Router._tracer`. Extend it to also emit `tracer.stage(...)` for the four work stages and `tracer.marker(...)` at each review prompt. The server's `Connection` class — which currently mirrors every WS message into `events.jsonl` and folds spawn edges into `parent_id` — becomes a thin live-mode dispatcher. The frontend's `replayAdapter` collapses to identity passthroughs because events are now canonical agrex.

**Tech Stack:** Python 3.12 (decisionlab), TypeScript/React (web), `agrex>=0.7.0` (Python + JS), FastAPI WS layer, `shared.storage` for S3.

Spec: `phase1-pablo/docs/superpowers/specs/2026-04-29-trace-as-canonical-replay-source.md`.

---

## Pre-flight context (read before starting)

### What's already in place

`Router._tracer` (an `agrex.Tracer`) is created in `Router.run()` via `_init_trace(run_id)` and finalized via `_finalize_trace(run_id)`. Every graph delta in `_do_research`, `_do_formalize`, `_do_reason`, `_do_build` calls a tracer method then forwards the same canonical event over the WS via `_send_event(self._tracer.events()[-1])`.

What still goes through `_send_event` directly (no tracer involvement):

- `_emit_agents()` — `{"type": "agents", "agents": [...]}` — UI initialization. **Stays live-only**, not in trace, replay reconstructs the panel from agent-typed nodes.
- The two `stage_change` emits in `_run_loop` (running + done) — **replaced in Task 1**.
- `review_request` / `review_decision` events emitted from `web_feedback.py` and from `Connection.handle_review_response` — **for `review_request` we add a `tracer.marker(...)` in Task 1**. The `review_decision` event currently fires from `Connection.handle_review_response` for replay reconstruction; after Task 1, the decision is reflected by node updates that follow, so the explicit `review_decision` emit can stay for live UI dispatch but doesn't need to be persisted in the trace.

### Why this matters

After `Tasks 3-6` of the prior agrex-py-integration plan, the canonical agrex shape (`{type, parentId, metadata}`) is what reaches the WS. The frontend's `replayAdapter` still translates from the OLD shape (`{kind, parent_id, meta}`), so live runs render with `type: undefined` and `parentId: undefined` — broken. This plan fixes that by simplifying the adapter to identity, which only works once the events on the wire are canonical agrex (already true for graph deltas; we extend to stage + review markers in Task 1).

### Server `Connection` quirks to preserve

`Connection` (server.py:60-258) carries reconnection state — `nodes`, `edges`, `current_stage`, `pending_review` — that gets pushed to a new socket on resync. We keep all of that. We only remove:

- `_logger`, `_store`, `_seq`, `_ensure_logger`, `_flush_log` (event-log persistence)
- `_pending_node_add` + `_is_spawn_for` (legacy spawn-edge folding — agrex emits `parentId` inline so this is dead code)
- The terminal-event flush path

### Inventory of files touched

```bash
grep -rn "EventLogger\|S3EventStore\|_pending_node_add\|_is_spawn_for\|fetchRunEvents\|/api/runs/.*events\|events\.jsonl\|stage_change" \
  phase1-pablo/src phase1-pablo/web/src phase1-pablo/tests
```

Run this before starting to confirm no surprises. Expected hits:

| File | What |
|---|---|
| `src/decisionlab/router.py` | 2× `stage_change` emits in `_run_loop` (Task 1) |
| `src/decisionlab/server.py` | `Connection` plumbing + `stage_change` bookkeeping → `stage` (Task 2), `/events` route (Task 3) |
| `src/decisionlab/runtime/event_logger.py` | delete (Task 4) |
| `src/decisionlab/runtime/event_store.py` | delete (Task 4) |
| `src/decisionlab/mock_server.py` | full overhaul — `stage_change` → `stage`, drop synthetic `review_decision`, migrate node/edge shape to canonical agrex (Task 7) |
| `web/src/lib/replayAdapter.ts` | reducer simplification (Task 5) |
| `web/src/App.tsx` | rename call site (Task 5) |
| `web/src/types.ts` | TS discriminated union — replace `stage_change` / `review_request` / `review_decision` with `stage` / `marker` (Task 5) |
| `web/src/hooks/useWebSocket.ts` | live dispatch — `case "stage_change":` → `case "stage":` (Task 5) |
| `tests/test_event_logger.py` | delete (Task 4) |
| `tests/test_event_store.py` | delete (Task 4) |
| `tests/test_server_event_log.py` | delete (Task 4) |
| `tests/test_server.py` | update `stage_change` bookkeeping assertions → `stage` (Task 2) |
| `tests/test_router_partial_runs.py::test_partial_run_uploads_agrex_trace_artifact` | extend (Task 6) |

---

## File Structure

**Modify:**
- `phase1-pablo/src/decisionlab/router.py` — `_run_loop` emits stage + review marker via tracer.
- `phase1-pablo/src/decisionlab/server.py` — strip EventLogger plumbing from `Connection`; replace `/events` route with `/trace`.
- `phase1-pablo/src/decisionlab/mock_server.py` — rename mock `/events` route to `/trace`.
- `phase1-pablo/web/src/lib/replayAdapter.ts` — collapse `labReducers` to identity; consume agrex `stage`/`marker` events; rename `fetchRunEvents` → `fetchRunTrace`.
- `phase1-pablo/web/src/App.tsx` — update import + call site.
- `phase1-pablo/tests/test_router_partial_runs.py` — extend the existing trace-artifact test to assert `stage` and `marker` events.

**Delete:**
- `phase1-pablo/src/decisionlab/runtime/event_logger.py`
- `phase1-pablo/src/decisionlab/runtime/event_store.py`
- `phase1-pablo/tests/test_event_logger.py`
- `phase1-pablo/tests/test_event_store.py`
- `phase1-pablo/tests/test_server_event_log.py`

---

## Task 1: Router emits `stage` + review `marker` events via tracer

**Files:**
- Modify: `phase1-pablo/src/decisionlab/router.py` (the `_run_loop` method around line 654)

- [ ] **Step 1: Read the current `_run_loop` body to anchor the edit**

```bash
grep -n "async def _run_loop\|stage_change" /Users/ppazosp/projects/labTFG/phase1-pablo/src/decisionlab/router.py
```

Expected: `_run_loop` definition near line 654, two `stage_change` `_send_event` calls inside it (around lines 678 and 686).

- [ ] **Step 2: Replace the two `stage_change` calls with tracer-driven stage + review marker emits**

In `_run_loop`, find:

```python
        while self.state.stage != Stage.DONE:
            current_stage = self.state.stage  # capture before handler
            handler = handlers[current_stage]
            await self._send_event(
                {
                    "type": "stage_change",
                    "stage": current_stage.value,
                    "status": "running",
                }
            )
            await handler()
            await self._send_event(
                {
                    "type": "stage_change",
                    "stage": current_stage.value,
                    "status": "done",
                }
            )
```

Replace with:

```python
        # Stages worth annotating on the timeline (the four work stages).
        # Memory and review sub-stages are intentionally excluded — they
        # would be timeline noise.
        _TIMELINE_WORK_STAGES = {
            Stage.RESEARCH,
            Stage.FORMALIZE,
            Stage.REASON,
            Stage.BUILD,
        }
        _REVIEW_STAGES = {
            Stage.REVIEW_RESEARCH,
            Stage.REVIEW_FORMALIZE,
            Stage.REVIEW_REASON,
            Stage.REVIEW_BUILD,
        }

        while self.state.stage != Stage.DONE:
            current_stage = self.state.stage  # capture before handler
            handler = handlers[current_stage]

            if current_stage in _TIMELINE_WORK_STAGES:
                self._tracer.stage(current_stage.value)
                await self._send_event(self._tracer.events()[-1])
            elif current_stage in _REVIEW_STAGES:
                # Drop the "review_" prefix so the marker kind reads
                # "review_research" not "review_review_research".
                stage_name = current_stage.value.removeprefix("review_")
                self._tracer.marker(f"review_{stage_name}", color="#fbbf24")
                await self._send_event(self._tracer.events()[-1])

            await handler()
```

Note the deletions:
- The two `stage_change` emits are gone.
- The `await handler()` shifts to its new home directly after the gating.

- [ ] **Step 3: Move the work-stage / review-stage sets to module level**

The constants `_TIMELINE_WORK_STAGES` and `_REVIEW_STAGES` belong with the other `_MEMORY_STAGE_OF` / `_REVIEW_AFTER_MEMORY` mappings near the top of the file (around line 70-90). Cut them from the inside of `_run_loop` and add at module level after `_REVIEW_AFTER_MEMORY`:

```python
# Work stages that emit a `tracer.stage(...)` timeline event (memory and
# review sub-stages are intentionally excluded — they'd be timeline noise).
_TIMELINE_WORK_STAGES = {
    Stage.RESEARCH,
    Stage.FORMALIZE,
    Stage.REASON,
    Stage.BUILD,
}

# Review stages that emit a yellow `tracer.marker(...)` at the prompt.
_REVIEW_STAGES = {
    Stage.REVIEW_RESEARCH,
    Stage.REVIEW_FORMALIZE,
    Stage.REVIEW_REASON,
    Stage.REVIEW_BUILD,
}
```

Inside `_run_loop`, the gating reads from those module-level constants.

- [ ] **Step 4: Run the tracer-aware unit tests**

```bash
cd /Users/ppazosp/projects/labTFG/phase1-pablo
uv run --group dev pytest tests/test_router_trace.py tests/test_router_review_build.py tests/test_router_review_reason.py -v
```

Expected: all pass. The lifecycle tests don't drive a full run, so they're unaffected by the new stage/marker emits.

- [ ] **Step 5: Run the agent-stage suite to confirm nothing broke**

```bash
uv run --group dev pytest tests/agents -v
```

Expected: 100% pass.

- [ ] **Step 6: Run ruff check + format**

```bash
uv run --group dev ruff check src/decisionlab/router.py
uv run --group dev ruff format src/decisionlab/router.py
```

Expected: no new errors. The 6 pre-existing ruff issues from the prior plan are still present and acceptable (untouched code).

- [ ] **Step 7: Commit**

```bash
cd /Users/ppazosp/projects/labTFG
git add phase1-pablo/src/decisionlab/router.py
git commit -m "feat[decisionlab]: emit stage + review markers via agrex tracer"
```

---

## Task 2: Strip `EventLogger` plumbing from `Connection`

Remove the events.jsonl mirror and the legacy spawn-edge buffering. Keep reconnection state (`nodes`, `edges`, `current_stage`, `pending_review`).

**Files:**
- Modify: `phase1-pablo/src/decisionlab/server.py` (the `Connection` class around lines 60-258)

- [ ] **Step 1: Inspect the current `Connection` to anchor the changes**

```bash
grep -n "class Connection\|_logger\|_store\|_seq\|_pending_node_add\|_is_spawn_for\|_ensure_logger\|_flush_log" /Users/ppazosp/projects/labTFG/phase1-pablo/src/decisionlab/server.py
```

Expected hits within `Connection` (lines 60-258) plus `_is_spawn_for` defined as a module-level helper above the class.

- [ ] **Step 2: Read the full `Connection` class body so the edit is grounded**

```bash
sed -n '60,260p' /Users/ppazosp/projects/labTFG/phase1-pablo/src/decisionlab/server.py
```

- [ ] **Step 3: Delete the legacy fields from `Connection.__init__`**

Find the `Connection.__init__` and remove these four lines:

```python
        self._logger = None
        self._store = None
        self._seq = 0
        self._pending_node_add: dict | None = None
```

Keep these (state for reconnection):

```python
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.current_stage: str | None = None
        self.pending_review: dict | None = None
        self.run_id: str | None = None
```

- [ ] **Step 4: Delete `_resolve_storage`, `_ensure_logger`, `_flush_log`**

These methods become unused. Find each and delete:

```python
    def _resolve_storage(self):
        ...

    def _ensure_logger(self, run_id: str) -> None:
        ...

    async def _flush_log(self) -> None:
        ...
```

- [ ] **Step 5: Simplify `Connection.emit`**

Find the current `async def emit(self, msg: dict) -> None:` (around line 136) and replace its body. Current shape uses `_pending_node_add` to defer node_add until a spawn `edge_add` arrives. Replace the whole method with a passthrough to `_emit_raw`:

```python
    async def emit(self, msg: dict) -> None:
        """Send *msg* to the WS client and update reconnection state."""
        await self._emit_raw(msg)
```

Also delete `flush_pending_node_add` (no longer needed):

```python
    async def flush_pending_node_add(self) -> None:
        ...
```

- [ ] **Step 6: Simplify `_emit_raw`**

Current `_emit_raw` does run-start log init, state bookkeeping, persist-to-EventLogger, send_json, and a flush on terminal events. Replace its body with state bookkeeping + send_json only:

```python
    async def _emit_raw(self, msg: dict) -> None:
        msg_type = msg.get("type")

        # -- state bookkeeping for reconnection --
        if msg_type == "node_add":
            self.nodes.append(msg["node"])
        elif msg_type == "edge_add":
            self.edges.append(msg["edge"])
        elif msg_type == "node_update":
            for n in self.nodes:
                if n["id"] == msg["id"]:
                    n["status"] = msg["status"]
                    break
        elif msg_type == "stage":
            self.current_stage = msg.get("label")
        elif msg_type == "review_request":
            self.pending_review = msg
        elif msg_type == "graph_clear":
            self.nodes.clear()
            self.edges.clear()
        elif msg_type == "run_start":
            self.run_id = msg.get("run_id")
        elif msg_type == "pipeline_done":
            self.pending_review = None

        # -- send over WS --
        if self.ws is not None:
            try:
                await self.ws.send_json(msg)
            except Exception as exc:
                logger.warning(
                    "WS send_json failed for type=%r: %s", msg_type, exc
                )
```

Note: `stage_change` is replaced by `stage` (the agrex event type — the bookkeeping reads `msg["label"]`, since `tracer.stage("research")` produces `{"type": "stage", "label": "research", ...}`).

- [ ] **Step 7: Simplify `cancel_and_flush`**

Currently calls `flush_pending_node_add` and `_flush_log`. With both gone, the method becomes a no-op and can be deleted. Find every caller:

```bash
grep -n "cancel_and_flush" /Users/ppazosp/projects/labTFG/phase1-pablo/src/decisionlab/server.py
```

Delete the method definition. Delete each caller's `await connection.cancel_and_flush()` line.

- [ ] **Step 8: Simplify `handle_review_response`**

Currently emits a `review_decision` event into the WS+log (line 245). Keep the WS dispatch behavior but stop fabricating a synthetic event. The pipeline still needs the dispatch (`_dispatch(stage, payload)`) so the awaiting handler resumes. Replace with:

```python
    async def handle_review_response(self, data: dict) -> None:
        """Dispatch the user's review decision to the waiting pipeline.

        The decision itself is reflected in subsequent graph deltas (node
        updates, re-run subgraphs), so no separate `review_decision` event
        is emitted to the trace.
        """
        from decisionlab.web_feedback import handle_review_response as _dispatch

        _dispatch(data["stage"], data["data"])
```

- [ ] **Step 9: Delete `_is_spawn_for` helper**

```bash
grep -n "_is_spawn_for\|def _is_spawn_for" /Users/ppazosp/projects/labTFG/phase1-pablo/src/decisionlab/server.py
```

Find the module-level helper and delete its definition. With `flush_pending_node_add` and the buffer machinery gone, no callers remain.

- [ ] **Step 10: Update `tests/test_server.py` for the `stage` rename**

Find each call passing `{"type": "stage_change", "stage": "..."}` to `manager.emit(...)` (around lines 92-94 and 122-124) and replace with the agrex shape:

```python
        await manager.emit({"type": "stage", "label": "RESEARCH"})
```

Also rename the test functions if they reference `stage_change` in their name:
- `test_emit_stage_change_records_current` → `test_emit_stage_records_current`

Verify by re-running the test name search:

```bash
grep -n "stage_change" tests/test_server.py
```

Expected: no remaining hits.

- [ ] **Step 11: Run the server unit tests + smoke tests**

```bash
cd /Users/ppazosp/projects/labTFG/phase1-pablo
uv run --group dev pytest tests/test_server.py tests/test_smoke.py -v
```

Expected: pass. Some assertions may have referenced `_logger` / `_seq` / `_pending_node_add` — if a test fails for that reason, the test belongs to `test_server_event_log.py` (Task 4 deletes it) or has a stale fixture; check before patching.

- [ ] **Step 12: Run ruff + format**

```bash
uv run --group dev ruff check src/decisionlab/server.py tests/test_server.py
uv run --group dev ruff format src/decisionlab/server.py tests/test_server.py
```

- [ ] **Step 13: Commit**

```bash
cd /Users/ppazosp/projects/labTFG
git add phase1-pablo/src/decisionlab/server.py phase1-pablo/tests/test_server.py
git commit -m "refactor[decisionlab]: drop EventLogger plumbing from Connection"
```

---

## Task 3: Replace `/api/runs/{run_id}/events` with `/api/runs/{run_id}/trace`

**Files:**
- Modify: `phase1-pablo/src/decisionlab/server.py` (the route around line 546)
- Modify: `phase1-pablo/src/decisionlab/mock_server.py` (the parallel mock route around line 1526)

- [ ] **Step 1: Replace the FastAPI route in `server.py`**

Find:

```python
@app.get("/api/runs/{run_id}/events")
async def get_run_events(run_id: str):
    """Stream the recorded WS event stream for a run (NDJSON).

    Returns 409 if the run is still in progress (live observation should use
    the WS), 404 if no event log exists.
    """
    import uuid

    from fastapi.responses import PlainTextResponse
    from sqlalchemy import select

    import shared
    from shared.models import Run

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

Replace with:

```python
@app.get("/api/runs/{run_id}/trace")
async def get_run_trace(run_id: str):
    """Stream the agrex trace.jsonl for a run.

    Returns 409 if the run is still in progress (live observation should use
    the WS), 404 if no trace exists (e.g. pre-trace runs).
    """
    import uuid

    from fastapi.responses import PlainTextResponse
    from sqlalchemy import select

    import shared
    from shared.models import Run

    async with shared.db.get_session() as session:
        result = await session.execute(
            select(Run.status).where(Run.id == uuid.UUID(run_id))
        )
        row = result.first()
    if row is not None and row[0] == "running":
        raise HTTPException(status_code=409, detail="Run still in progress")

    key = f"research/{run_id}/trace.jsonl"
    if not await shared.storage.exists(key):
        raise HTTPException(status_code=404, detail="Trace not found")
    body = await shared.storage.get_text(key)
    return PlainTextResponse(body, media_type="application/x-ndjson")
```

- [ ] **Step 2: Replace the parallel route in `mock_server.py`**

Find around line 1526:

```python
@app.get("/api/runs/{run_id}/events")
async def get_run_events(run_id: str):
    """Stream the recorded event stream for a run (NDJSON)."""
    rec = _run_records.get(run_id)
    if rec and rec["status"] == "running":
        raise HTTPException(status_code=409, detail="Run still in progress")
    events = _run_events.get(run_id)
    if not events:
        raise HTTPException(status_code=404, detail="Event log not found")
    body = "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in events)
    return PlainTextResponse(body, media_type="application/x-ndjson")
```

Replace function name and docstring (keep the body — the mock simply replays the in-memory event list, the rename is purely cosmetic):

```python
@app.get("/api/runs/{run_id}/trace")
async def get_run_trace(run_id: str):
    """Stream the recorded trace for a run (NDJSON)."""
    rec = _run_records.get(run_id)
    if rec and rec["status"] == "running":
        raise HTTPException(status_code=409, detail="Run still in progress")
    events = _run_events.get(run_id)
    if not events:
        raise HTTPException(status_code=404, detail="Trace not found")
    body = "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in events)
    return PlainTextResponse(body, media_type="application/x-ndjson")
```

- [ ] **Step 3: Run server tests**

```bash
cd /Users/ppazosp/projects/labTFG/phase1-pablo
uv run --group dev pytest tests/test_server.py tests/test_runs_api.py -v 2>&1 | tail -20
```

Expected: pass for any tests not deleted in Task 4. `test_runs_api.py` may fail if it asserts on `/api/runs/.../events` — patch the URL inline if so.

- [ ] **Step 4: Commit**

```bash
cd /Users/ppazosp/projects/labTFG
git add phase1-pablo/src/decisionlab/server.py phase1-pablo/src/decisionlab/mock_server.py
git commit -m "feat[decisionlab]: replace /events route with /trace serving trace.jsonl"
```

---

## Task 4: Delete `event_logger`, `event_store`, and their tests

Now that nothing in `src/` references them, the modules and their dedicated tests can go.

**Files:**
- Delete: `phase1-pablo/src/decisionlab/runtime/event_logger.py`
- Delete: `phase1-pablo/src/decisionlab/runtime/event_store.py`
- Delete: `phase1-pablo/tests/test_event_logger.py`
- Delete: `phase1-pablo/tests/test_event_store.py`
- Delete: `phase1-pablo/tests/test_server_event_log.py`

- [ ] **Step 1: Verify no remaining `src/` references**

```bash
cd /Users/ppazosp/projects/labTFG/phase1-pablo
grep -rn "EventLogger\|S3EventStore\|event_logger\|event_store" src/
```

Expected: no output. If anything remains, investigate before deleting — that import is the actual blocker.

- [ ] **Step 2: Delete the modules and tests**

```bash
git rm src/decisionlab/runtime/event_logger.py
git rm src/decisionlab/runtime/event_store.py
git rm tests/test_event_logger.py
git rm tests/test_event_store.py
git rm tests/test_server_event_log.py
```

- [ ] **Step 3: Run the full safe test suite to confirm no broken imports**

```bash
uv run --group dev pytest tests/ \
  --ignore=tests/test_router_partial_runs.py \
  --ignore=tests/test_routing_llm_integration.py \
  --ignore=tests/test_runs_api.py \
  --ignore=tests/test_cli.py \
  --ignore=tests/denis -q
```

Expected: all pass. Total count drops by however many tests lived in the three deleted files (~30-40 fewer).

- [ ] **Step 4: Commit**

```bash
cd /Users/ppazosp/projects/labTFG
git commit -m "refactor[decisionlab]: drop dead event_logger / event_store modules"
```

---

## Task 5: Simplify `replayAdapter.ts` to canonical-agrex passthrough

The reducers can now drop their translation layer because the events on the wire are already canonical agrex. `extractLabMarkers` and `labStepBoundaries` switch to consuming agrex `stage` and `marker` event types.

**Files:**
- Modify: `phase1-pablo/web/src/lib/replayAdapter.ts`

- [ ] **Step 1: Replace the file body wholesale**

Open `/Users/ppazosp/projects/labTFG/phase1-pablo/web/src/lib/replayAdapter.ts` and replace its contents with:

```typescript
import {
  defaultStepBoundaries,
  type AgrexEdge,
  type AgrexEvent,
  type AgrexMarker,
  type AgrexNode,
  type EventReducer,
} from "@ppazosp/agrex";
import type { Stage } from "../types";

// Events on the WS and in trace.jsonl are canonical agrex shape (`type`,
// `parentId`, `metadata`). The reducers are identity passthroughs — agrex's
// own renderer + timeline consume the trace directly.

export const labReducers: Record<string, EventReducer> = {
  node_add(store, ev) {
    const node = ev.node as AgrexNode | undefined;
    if (node) store.addNode(node);
  },
  edge_add(store, ev) {
    const edge = ev.edge as AgrexEdge | undefined;
    if (edge) store.addEdge(edge);
  },
  graph_clear(store) {
    store.clear();
  },
  state_sync(store, ev) {
    const nodes = (ev.nodes as AgrexNode[] | undefined) ?? [];
    const edges = (ev.edges as AgrexEdge[] | undefined) ?? [];
    store.loadJSON({ nodes, edges });
  },
};

export interface StageMarker extends AgrexMarker {
  kind: "stage";
  stage: Stage;
}

export interface ReviewMarker extends AgrexMarker {
  kind: "review";
  stage: Stage;
}

const REVIEW_MARKER_PREFIX = "review_";

/**
 * Extract stage + review markers from the agrex trace.
 *
 * - `stage` events become stage markers on the timeline (cursor at the index
 *   of the stage event itself).
 * - `marker` events whose `kind` starts with `review_` become yellow review
 *   markers (cursor at the prompt index).
 */
export function extractLabMarkers(events: AgrexEvent[]): AgrexMarker[] {
  const out: AgrexMarker[] = [];
  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    if (ev.type === "stage") {
      const label = String(ev.label ?? "");
      const m: StageMarker = {
        cursor: i,
        kind: "stage",
        label,
        stage: label as Stage,
      };
      out.push(m);
    } else if (
      ev.type === "marker" &&
      typeof ev.kind === "string" &&
      ev.kind.startsWith(REVIEW_MARKER_PREFIX)
    ) {
      const stage = ev.kind.slice(REVIEW_MARKER_PREFIX.length) as Stage;
      const m: ReviewMarker = {
        cursor: i,
        kind: "review",
        label: `Review: ${stage}`,
        color: typeof ev.color === "string" ? ev.color : "#fbbf24",
        stage,
      };
      out.push(m);
    }
  }
  return out;
}

// Step boundaries: advance one visible graph delta per step. Start from the
// agrex defaults and add `stage` events so scrubbing aligns with pipeline
// phases.
const EXTRA_BOUNDARY_TYPES = new Set(["stage", "graph_clear", "state_sync"]);

export function labStepBoundaries(events: AgrexEvent[]): number[] {
  const boundaries = new Set<number>(defaultStepBoundaries(events));
  for (let i = 0; i < events.length; i++) {
    if (EXTRA_BOUNDARY_TYPES.has(events[i].type)) boundaries.add(i + 1);
  }
  return [...boundaries].sort((a, b) => a - b);
}

/**
 * Fetch and parse the agrex trace.jsonl for a run.
 */
export async function fetchRunTrace(runId: string): Promise<AgrexEvent[]> {
  const resp = await fetch(`/api/runs/${runId}/trace`);
  if (!resp.ok) throw new Error(`Failed to load trace for run ${runId}`);
  const text = await resp.text();
  return text
    .split("\n")
    .filter((ln) => ln.trim())
    .map((ln) => JSON.parse(ln) as AgrexEvent);
}
```

Notes:
- Removed: `BackendNode`, `BackendEdge`, `toAgrexNode`, `toAgrexEdge`, `injectSpawnParents`, the legacy `review_request` / `review_decision` pairing logic.
- `extractLabMarkers` is now linear and stateless.
- `fetchRunEvents` is renamed to `fetchRunTrace`.

- [ ] **Step 2: Update `web/src/types.ts` — replace `stage_change`/`review_decision` arms with `stage`/`marker`**

Open `/Users/ppazosp/projects/labTFG/phase1-pablo/web/src/types.ts`. Find the `ServerMessage` discriminated union (around lines 58-82). Make these specific changes:

Remove these arms:
```typescript
  | { type: "stage_change"; stage: Stage; status: StageStatus }
  | { type: "review_decision"; stage: Stage; approved: Record<string, boolean> | unknown };
```

Add these arms (anywhere in the union, but adjacent to other agrex-canonical event types reads cleanly):
```typescript
  | { type: "stage"; ts: number; label: string; color?: string }
  | { type: "marker"; ts: number; kind: string; label?: string; color?: string }
```

Leave the `review_request` arms alone — those still fire for the live UI (the human-in-the-loop dialog still needs to show).

- [ ] **Step 3: Update `web/src/hooks/useWebSocket.ts` — replace `stage_change` case with `stage`**

Open `/Users/ppazosp/projects/labTFG/phase1-pablo/web/src/hooks/useWebSocket.ts`. Find the `case "stage_change":` arm (around line 109):

```typescript
    case "stage_change":
      return {
        ...state,
        stages: { ...state.stages, [msg.stage]: msg.status },
        currentStage: msg.status === "running" ? msg.stage : state.currentStage,
      };
```

Replace with a `case "stage":` that synthesizes the running/done transitions client-side. The agrex `stage` event has no `status` field, so when a new stage arrives we mark the previous `currentStage` as `done` and the new one as `running`:

```typescript
    case "stage": {
      const newStage = msg.label as Stage;
      const stages = { ...state.stages, [newStage]: "running" as const };
      // The previous "running" stage transitions to "done" when a new
      // stage starts. Memory and review sub-stages don't emit `stage`,
      // so the previous timeline marker is always a work stage.
      if (state.currentStage && state.currentStage !== newStage) {
        stages[state.currentStage] = "done";
      }
      return { ...state, stages, currentStage: newStage };
    }
```

Leave the `case "review_request":` arm alone (still needed for the live review dialog). No new case needed for `marker` — markers are timeline annotations, not state transitions.

- [ ] **Step 4: Update the App.tsx import + call site**

Open `/Users/ppazosp/projects/labTFG/phase1-pablo/web/src/App.tsx` and find:

```typescript
import {
  ...
  fetchRunEvents,
  ...
} from "./lib/replayAdapter";
```

Rename `fetchRunEvents` → `fetchRunTrace`. Then find the call site (around line 367):

```typescript
      await replay.load(fetchRunEvents(runIdSel));
```

Rename to `fetchRunTrace`:

```typescript
      await replay.load(fetchRunTrace(runIdSel));
```

- [ ] **Step 5: Type-check the frontend**

```bash
cd /Users/ppazosp/projects/labTFG/phase1-pablo/web
pnpm tsc --noEmit 2>&1 | tail -20
```

Expected: no errors. The simplified reducers, the renamed `ServerMessage` arms, and the new `case "stage":` should all typecheck.

- [ ] **Step 6: Lint the frontend**

```bash
pnpm lint 2>&1 | tail -10
```

Expected: clean (or only pre-existing warnings).

- [ ] **Step 7: Commit**

```bash
cd /Users/ppazosp/projects/labTFG
git add phase1-pablo/web/src/lib/replayAdapter.ts phase1-pablo/web/src/App.tsx phase1-pablo/web/src/types.ts phase1-pablo/web/src/hooks/useWebSocket.ts
git commit -m "refactor[web]: consume canonical agrex stage/marker events"
```

---

## Task 6: E2E verification + extended trace test

Live verification in a browser plus an integration test that asserts the trace contains stage and review-marker events.

**Files:**
- Modify: `phase1-pablo/tests/test_router_partial_runs.py`

- [ ] **Step 1: Extend `test_partial_run_uploads_agrex_trace_artifact`**

Find the existing test (added in the prior plan). It already uses a mocked `_do_research` that calls `tracer.agent` + `tracer.done`. Extend the assertions to confirm the loop's stage + review marker emit reach the trace.

Open `phase1-pablo/tests/test_router_partial_runs.py`. Find:

```python
        events = parse_trace(content)
        assert any(
            e["type"] == "node_add" and e["node"]["id"] == "researcher"
            for e in events
        )
        assert any(
            e["type"] == "node_update"
            and e["id"] == "researcher"
            and e["status"] == "done"
            for e in events
        )
        assert all("ts" in e for e in events)
```

Append the two new assertions:

```python
        # Task 1: research stage emits a `tracer.stage(...)` event into the trace.
        assert any(
            e["type"] == "stage" and e.get("label") == "research" for e in events
        )
        # Task 1: REVIEW_RESEARCH transition emits a yellow review marker.
        assert any(
            e["type"] == "marker" and e.get("kind") == "review_research"
            for e in events
        )
```

- [ ] **Step 2: Run the integration test (requires local infra)**

```bash
cd /Users/ppazosp/projects/labTFG/phase1-pablo
uv run --group dev pytest tests/test_router_partial_runs.py::test_partial_run_uploads_agrex_trace_artifact -v
```

Expected: pass. Requires postgres + minio running (`docker compose up -d postgres minio neo4j qdrant`) and migrations applied (`cd shared && uv run alembic upgrade head`).

- [ ] **Step 3: Run the full safe suite**

```bash
uv run --group dev pytest tests/ \
  --ignore=tests/test_routing_llm_integration.py \
  --ignore=tests/test_runs_api.py \
  --ignore=tests/test_cli.py \
  --ignore=tests/denis -q
```

Expected: all pass. Tally check: prior plan landed at 596 passing (601 with infra up); this plan deletes 5 test files (~30-40 tests) and adds 2 assertions to 1 test, so expect ~560-570 passing.

- [ ] **Step 4: Browser smoke test (manual)**

```bash
# Terminal 1 — backend
cd /Users/ppazosp/projects/labTFG/phase1-pablo
uv run uvicorn decisionlab.server:app --port 8000

# Terminal 2 — frontend
cd /Users/ppazosp/projects/labTFG/phase1-pablo/web
pnpm dev
```

Open http://localhost:5173. Verify:

1. Start a fresh run (`/run "any prompt" --until research` from the chat or an equivalent command). The graph should render the Researcher node, the timeline should advance one step per graph delta, the stage marker should appear when the research stage starts, and a yellow marker should appear at the review prompt.
2. Cancel or let it complete. Click the run in PastRunsList (bottom-right). The graph + timeline should reproduce identically.
3. Drop the artifact on the external viewer for a third sanity check:

```bash
# Pull the trace
mc cp myminio/labtfg/research/<run_id>/trace.jsonl /tmp/trace.jsonl
# (or use the new /api/runs/<run_id>/trace endpoint via curl)
```

Open https://agrex.ppazosp.dev and drop the file — the same graph should render.

- [ ] **Step 5: Update the integration doc**

Open `phase1-pablo/docs/agrex-integration.md` and replace the "Trace recording" section's WS-extension paragraph with:

```markdown
The trace also carries pipeline-level annotations:

- `stage` events for each work stage (research / formalize / reason / build), emitted from `Router._run_loop` via `tracer.stage(...)`. They appear as stage markers on the agrex timeline.
- `marker` events with `kind: "review_<stage>"` for each human-review prompt, emitted from `Router._run_loop` via `tracer.marker(...)` with `color: "#fbbf24"`. They appear as yellow markers on the timeline.

Replay in the in-app viewer fetches `GET /api/runs/{run_id}/trace`. Drop the file on https://agrex.ppazosp.dev for the external viewer.
```

- [ ] **Step 6: Commit**

```bash
cd /Users/ppazosp/projects/labTFG
git add phase1-pablo/tests/test_router_partial_runs.py phase1-pablo/docs/agrex-integration.md
git commit -m "test[decisionlab]: assert stage + review markers in trace artifact + docs"
```

---

## Task 7: Overhaul `mock_server.py` to emit canonical agrex events

The frontend mock backend needs to produce the same canonical agrex shape as the real backend, otherwise the simplified `replayAdapter` won't render its events correctly. Mechanical but voluminous rewrite — ~25 emit sites in the mocked pipeline plus the `_seed_past_run` static fixture.

**Files:**
- Modify: `phase1-pablo/src/decisionlab/mock_server.py`

- [ ] **Step 1: Inventory the work**

```bash
cd /Users/ppazosp/projects/labTFG/phase1-pablo
grep -n "stage_change\|parent_id\|edge_kind\|kind\":\|review_decision\|_pending_node_add\|_is_spawn_for" src/decisionlab/mock_server.py | wc -l
```

Expected: 80-100 hits across the file. Each falls into one of the rewrite rules below.

- [ ] **Step 2: Apply rewrite rules**

Apply these rules across `mock_server.py`. Each rule is mechanical; verify after each pass with the matching grep.

**Rule A — `stage_change` (running) → `stage` event.** For every emit of the form `{"type": "stage_change", "stage": "<name>", "status": "running"}`, replace with `{"type": "stage", "label": "<name>"}`. Then drop every emit with `"status": "done"` for work stages.

**Important exception:** The mocked pipeline emits `stage_change` for *all* stages, including memory and review sub-stages. After the refactor, only the four work stages (`research`, `formalize`, `reason`, `build`) should emit `stage` events. Sub-stage `stage_change` emits (like `review_research`, `memory_research`, etc.) are dropped entirely — replace them with a `marker` event for the review prompts (Rule E) and nothing for the memory ones.

```bash
grep -n '"type": "stage_change"' src/decisionlab/mock_server.py
```

For each match, decide:
- Work stage `running` → rewrite to `{"type": "stage", "label": "<name>"}`
- Work stage `done` → delete the line
- Memory sub-stage (any status) → delete
- Review sub-stage (any status) → delete (replaced in Rule E)

**Rule B — node shape: `kind` → `type`, `parent_id` → `parentId`, `meta` → `metadata`.**

For every node payload of the form:

```python
{
    "id": "X",
    "kind": "agent",
    "label": "Researcher",
    "parent_id": "Y",
    "status": "running",
    "meta": {...},
    "metadata": {...},
}
```

Rewrite to:

```python
{
    "id": "X",
    "type": "agent",
    "label": "Researcher",
    "parentId": "Y",
    "status": "running",
    "metadata": {**meta, **metadata},  # merge if both were present
}
```

When `meta` and `metadata` were both present (the legacy mock had both), merge them into a single `metadata` (later wins on key conflict — `metadata` wins, since `meta` was the labTFG-specific extension and `metadata` was forward-compat).

```bash
# Verify after rewrite
grep -nE '"kind":|"parent_id":|"meta":' src/decisionlab/mock_server.py
```

Expected after Rule B: zero matches (excluding string literals in tests or comments).

**Rule C — drop spawn `edge_add` emits.** Find every `{"type": "edge_add", "edge": {"source": "X", "target": "Y", "edge_kind": "spawn"}}` and delete the entry. Spawn relationships are now carried by the target node's `parentId`. Confirm Rule B already set `parentId` on the target node before deleting the spawn edge.

```bash
grep -nB 1 '"edge_kind": "spawn"' src/decisionlab/mock_server.py
```

For each hit, delete the surrounding `{"type": "edge_add", "edge": {...}}` block.

**Rule D — non-spawn `edge_add` shape.** For `edge_add` events whose `edge_kind` is `read` / `write` / `layout`, rewrite the edge payload to canonical agrex:

Before:
```python
{"type": "edge_add", "edge": {"source": "researcher", "target": "para-foraging", "edge_kind": "write"}}
```

After:
```python
{"type": "edge_add", "edge": {"id": "researcher-para-foraging", "source": "researcher", "target": "para-foraging", "type": "write"}}
```

(`AgrexEdge` requires an `id`. A `${source}-${target}` slug is fine for mocks.)

```bash
grep -n '"edge_kind"' src/decisionlab/mock_server.py
```

Expected after Rule D: zero matches.

**Rule E — review prompts emit a `marker`.** Where the mock currently emits `{"type": "stage_change", "stage": "review_X", "status": "running"}` and then `{"type": "review_request", ...}`, replace the stage_change with a marker:

Before (around line 1052):
```python
await emit({"type": "stage_change", "stage": "review_research", "status": "running"})
...
await emit({"type": "review_request", "stage": "review_research", "data": {...}})
...
await emit({"type": "stage_change", "stage": "review_research", "status": "done"})
```

After:
```python
await emit({"type": "marker", "kind": "review_research", "color": "#fbbf24"})
...
await emit({"type": "review_request", "stage": "review_research", "data": {...}})
# (no terminating stage_change — review_request remains for the live UI dialog;
#  the marker is the timeline annotation)
```

The four review stages (`review_research`, `review_formalize`, `review_reason`, `review_build`) all follow the same pattern.

**Rule F — drop synthetic `review_decision`.** Around line 723-730:

```python
await emit(
    {
        "type": "review_decision",
        "stage": stage,
        "approved": approved,
    }
)
```

Delete the emit. The decision is reflected in subsequent node updates and re-runs.

**Rule G — delete legacy buffering machinery.** Find and delete the `_is_spawn_for` helper, the `_pending_node_add` buffer field, and the buffering branches in the mock's emit function. Mirror of Task 2's Connection cleanup applied to the mock's `Connection`/`Manager` class.

```bash
grep -n "_is_spawn_for\|_pending_node_add\|flush_pending_node_add" src/decisionlab/mock_server.py
```

For each hit, delete the line or surrounding block.

**Rule H — bookkeeping: `stage_change` → `stage`.** Inside the mock's `emit` function (around line 693), rename the bookkeeping arm:

```python
elif msg_type == "stage_change":
    self.current_stage = msg.get("stage")
```

becomes:

```python
elif msg_type == "stage":
    self.current_stage = msg.get("label")
```

- [ ] **Step 3: Update `_seed_past_run` to canonical shape**

The static seed at `mock_server.py:445-555` uses every legacy shape that Rules A-D rewrite. Apply the same rewrites to the seed list. After the rewrite, the seed should look like:

```python
raw: list[dict] = [
    {"type": "run_start", "run_id": run_id},
    {"type": "stage", "label": "research"},
    {
        "type": "node_add",
        "node": {
            "id": "researcher",
            "type": "agent",
            "label": "Researcher",
            "status": "running",
            "metadata": {"startedAt": t_start},
        },
    },
    {
        "type": "node_add",
        "node": {
            "id": "ws-1",
            "type": "tool",
            "label": "web_search",
            "parentId": "researcher",
            "status": "done",
            "metadata": {
                "toolType": "web_search",
                "query": "optimal foraging under uncertainty",
                "startedAt": t_tool,
                "endedAt": t_tool + 800,
                "tokens": 940,
                "cost": 940 * 8e-6,
            },
        },
    },
    # spawn edge_add deleted (parentId on ws-1 carries it)
    {
        "type": "node_add",
        "node": {
            "id": "para-foraging",
            "type": "output",
            "label": "foraging.md",
            "parentId": "researcher",
            "status": "done",
            "metadata": {
                "stage": "research",
                "path": "foraging.md",
                "content": (
                    "# Optimal Foraging Theory\n\n"
                    "Agents choose patches to maximize long-run energy "
                    "intake net of travel and handling costs.\n"
                ),
            },
        },
    },
    {
        "type": "edge_add",
        "edge": {
            "id": "researcher-para-foraging",
            "source": "researcher",
            "target": "para-foraging",
            "type": "write",
        },
    },
    {
        "type": "node_update",
        "id": "researcher",
        "status": "done",
        "metadata": {
            "endedAt": t_done,
            "tokens": 7_850,
            "cost": 7_850 * 8e-6,
        },
    },
    # stage_change "research" "done" deleted
    {"type": "pipeline_done"},
]
```

- [ ] **Step 4: Final verification grep — no legacy shape left**

```bash
grep -nE '"type": "stage_change"|"kind":|"parent_id":|"meta":|"edge_kind":|review_decision|_pending_node_add|_is_spawn_for' src/decisionlab/mock_server.py
```

Expected: zero matches.

- [ ] **Step 5: Smoke-test the mock backend**

```bash
cd /Users/ppazosp/projects/labTFG/phase1-pablo
uv run uvicorn decisionlab.mock_server:app --port 8001
```

In another terminal:
```bash
curl -s http://localhost:8001/api/runs | head
curl -s http://localhost:8001/api/runs/<seed-run-id>/trace | head
```

Expected: the static seed run is listed, and its `/trace` endpoint returns canonical agrex NDJSON.

- [ ] **Step 6: Run the full safe test suite again**

```bash
uv run --group dev pytest tests/ \
  --ignore=tests/test_router_partial_runs.py \
  --ignore=tests/test_routing_llm_integration.py \
  --ignore=tests/test_runs_api.py \
  --ignore=tests/test_cli.py \
  --ignore=tests/denis -q
```

Expected: all pass. The mock_server has no dedicated tests (per earlier grep), but if any indirect test loads it, the new shape should still satisfy them.

- [ ] **Step 7: Commit**

```bash
cd /Users/ppazosp/projects/labTFG
git add phase1-pablo/src/decisionlab/mock_server.py
git commit -m "refactor[decisionlab]: mock_server emits canonical agrex events"
```

---

## Self-Review Checklist

Run through this once before handing off for execution:

**1. Spec coverage:**
- [x] `tracer.stage(...)` for the four work stages — Task 1
- [x] `tracer.marker(...)` for review prompts — Task 1
- [x] Drop EventLogger plumbing from `Connection` — Task 2
- [x] Drop legacy spawn-edge buffering (`_pending_node_add`, `_is_spawn_for`) — Task 2
- [x] `Connection` bookkeeping: `stage_change` → `stage` — Task 2
- [x] Update `tests/test_server.py` for `stage` event — Task 2
- [x] Replace `/events` route with `/trace` (real + mock servers) — Task 3
- [x] Delete `event_logger.py`, `event_store.py`, and their three tests — Task 4
- [x] Simplify `replayAdapter.ts` to canonical agrex passthrough — Task 5
- [x] Update `types.ts` (ServerMessage discriminated union) — Task 5
- [x] Update `useWebSocket.ts` (synthesize done-on-next-stage transition) — Task 5
- [x] Rename `fetchRunEvents` → `fetchRunTrace` and update App.tsx — Task 5
- [x] Extend `test_partial_run_uploads_agrex_trace_artifact` — Task 6
- [x] Browser smoke test — Task 6
- [x] Update `docs/agrex-integration.md` — Task 6
- [x] Mock server overhaul (mock_server.py to canonical agrex) — Task 7

**2. Type / API consistency:**
- `Router._tracer.stage(label)` — agrex Python signature `stage(label: str, *, color: str | None = None) -> None`. Matches.
- `Router._tracer.marker(kind, label=..., color=...)` — agrex Python signature `marker(kind: str, *, label: str | None = None, color: str | None = None) -> None`. Matches.
- WS `stage` event payload — `{"type": "stage", "ts": ..., "label": "research"}`. Bookkeeping reads `msg["label"]` — matches.
- WS `marker` event payload — `{"type": "marker", "ts": ..., "kind": "review_research", "color": "#fbbf24"}`. Frontend reads `ev.kind` — matches.

**3. Open execution-time questions:**
1. **Test dependence on `stage_change`** — if any non-deleted test asserts on the legacy `stage_change` event type, it needs updating to `stage`. Discover via `grep -rn "stage_change" tests/` after Task 1.
2. **`Connection.handle_review_response` callers** — Task 2 Step 8 stops emitting `review_decision`. Verify nothing else (live UI, other tests) depends on that synthetic event in the WS stream — `grep -rn "review_decision" phase1-pablo/`.

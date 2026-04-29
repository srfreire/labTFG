# Trace as the canonical replay source

## Goal

Make `trace.jsonl` (the agrex Tracer artifact) the single source of truth for past-run visualization in the web UI. Drop `events.jsonl` and the `EventLogger` plumbing entirely. Pipeline-level annotations (stage transitions, human-review prompts) ride on the tracer too — `tracer.stage()` / `tracer.marker()` — so the canonical artifact is also externally usable on https://agrex.ppazosp.dev with no extra layer.

## Motivation

`events.jsonl` predates agrex. Now that the Router emits canonical agrex events through `Router._tracer`, the WS message shape no longer matches the legacy `replayAdapter` translation (`kind` → `type`, `parent_id` → `parentId`), so the live UI is broken for new runs. Two options to repair: patch the adapter to handle both shapes (preserves the legacy artifact), or commit to the tracer and drop the legacy artifact. We pick the latter — fewer formats, single canonical artifact, sibling-compatible with the JS package.

## Scope

- **In:** Router emits stage/review marker events via tracer; remove `EventLogger`; replace `/api/runs/{run_id}/events` with `/api/runs/{run_id}/trace`; simplify `replayAdapter.ts` to consume canonical agrex events.
- **Out:** Download-trace UI button. Stage/review color theming. Backward compatibility with pre-this-PR runs (their `events.jsonl` files become orphaned in S3 — purge manually if desired).

## Current state (post-agrex-py-integration)

- Router emits graph-delta events via `Router._tracer` (`tracer.agent`, `tracer.done`, `tracer.error`). Each tracer call is followed by `await self._send_event(self._tracer.events()[-1])` so the same canonical agrex event reaches the WS and the trace file.
- `Router._send_event` also handles WS-extension messages (`agents`, `stage_change`, and indirectly `review_request` / `review_decision` emitted from `web_feedback.py`).
- `server.py`'s `Connection` class wraps the WS with `EventLogger` which mirrors every WS message into `research/{run_id}/events.jsonl` for replay.
- `GET /api/runs/{run_id}/events` serves that file. `replayAdapter.ts::fetchRunEvents` consumes it; `labReducers` translate the legacy shape to canonical agrex.

## Target state

- Router emits, in addition to graph deltas:
  - `tracer.stage(<stage>.value)` at the start of each of the four work stages (research / formalize / reason / build). Memory and review sub-stages do not emit `stage` — they'd be timeline noise.
  - `tracer.marker(f"review_{<stage>}", color="#fbbf24")` immediately before each `_review_<stage>` runs.
- `agents` WS event remains live-only (not persisted, not in trace). Replay reconstructs the agent panel from `node.type === "agent"` entries in the trace.
- `EventLogger` is removed from `server.py`. `Connection` no longer wraps WS messages for persistence. `events.jsonl` stops being written.
- New route: `GET /api/runs/{run_id}/trace` — reads `research/{run_id}/trace.jsonl` from S3, returns NDJSON. Same 409/404 contract as the old route.
- Old route `GET /api/runs/{run_id}/events` is removed.
- Frontend:
  - `replayAdapter.ts` `labReducers` collapse to identity passthroughs (events are already canonical agrex). `BackendNode`, `BackendEdge`, `toAgrexNode`, `toAgrexEdge`, `injectSpawnParents` are deleted.
  - `extractLabMarkers` reads `ev.type === "stage"` (timeline stage marker, picked up by agrex's default marker rendering) and `ev.type === "marker"` with `kind.startsWith("review_")` (yellow review dot).
  - `labStepBoundaries` switches from `stage_change` to `stage` events.
  - `fetchRunEvents` → `fetchRunTrace`, hits `/api/runs/{run_id}/trace`.

## File changes

### Backend

- `phase1-pablo/src/decisionlab/router.py`:
  - In `_run_loop`, drop the two `stage_change` `_send_event` calls. Replace with `tracer.stage(current_stage.value)` then `_send_event(...)`, gated on `current_stage in {RESEARCH, FORMALIZE, REASON, BUILD}`.
  - Same loop site: when `current_stage in {REVIEW_RESEARCH, REVIEW_FORMALIZE, REVIEW_REASON, REVIEW_BUILD}`, emit `tracer.marker(f"review_{current_stage.value.removeprefix('review_')}", color="#fbbf24")` and forward via `_send_event`. Centralizing here avoids touching each `_review_*` handler.
- `phase1-pablo/src/decisionlab/server.py`:
  - Delete the `_logger` and `_store` fields on `Connection` and the EventLogger/S3EventStore imports.
  - Replace `GET /api/runs/{run_id}/events` with `GET /api/runs/{run_id}/trace`. Reads `research/{run_id}/trace.jsonl`. Same 409-if-running, 404-if-missing semantics.
- Delete: `phase1-pablo/src/decisionlab/runtime/event_logger.py`, `phase1-pablo/src/decisionlab/runtime/event_store.py`. No other references in `src/` (grep-verified).

### Frontend

- `phase1-pablo/web/src/lib/replayAdapter.ts`:
  - Delete the legacy `BackendNode`/`BackendEdge` types, `toAgrexNode`, `toAgrexEdge`, `injectSpawnParents`.
  - Simplify `labReducers` (`node_add`, `edge_add`, `state_sync`) to identity passthroughs — the event payload is already an `AgrexNode`/`AgrexEdge`.
  - Update `extractLabMarkers` to consume `stage` and `marker` agrex event types.
  - Update `labStepBoundaries` to advance on `stage` events.
  - Rename `fetchRunEvents` → `fetchRunTrace`; hit `/api/runs/{run_id}/trace`.
- `phase1-pablo/web/src/App.tsx`:
  - Update import + call site.

### Tests

- `phase1-pablo/tests/test_event_logger.py`: delete with EventLogger.
- `phase1-pablo/tests/test_event_store.py`: delete with S3EventStore (only consumer was the deleted `Connection`).
- `phase1-pablo/tests/test_server_event_log.py`: delete (covers the same EventLogger plumbing being removed).
- `phase1-pablo/tests/test_router_partial_runs.py::test_partial_run_uploads_agrex_trace_artifact`: extend to assert presence of `stage` and at least one `marker` event in the trace.

## Risk

- **Breakage of past runs.** Pre-this-PR runs have `events.jsonl` but no `trace.jsonl`. Clicking such a run in PastRunsList will 404 from the new endpoint. Acceptable per migration option 1.
- **EventStore reuse.** If `EventStore` (the Postgres-backed event store) is referenced elsewhere (e.g. for analytics or for the `/api/runs/{run_id}/events` endpoint we're deleting), removal might break neighbors. Implementation step verifies via grep before deleting.
- **`agents` event reconstruction in replay.** The current frontend may surface the agent panel even before any agent node is added. After this change, the panel populates as agent nodes appear in the trace. Smaller visual delay; not blocking.

## Verification

- Live: open the web UI, run the pipeline, verify graph renders and updates correctly, stage scrubbing works, review markers appear.
- Replay: after a completed run, click it in PastRunsList. Same graph + timeline reproduce.
- Integration test: extended `test_partial_run_uploads_agrex_trace_artifact` checks the trace has `stage` and `marker` events.
- External viewer: download `trace.jsonl` from S3, drop on https://agrex.ppazosp.dev, confirm the same graph renders.

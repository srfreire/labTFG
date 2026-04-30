# WS Lifecycle Hardening (phase1-pablo, local-only) — ✅ DONE 2026-04-30

**Status:** All 4 PRs landed on `main`. Final commit range `9d535df..ce5a0e0` (plan + 4 fixes). 20 server pytest cases + 37 frontend vitest cases green.

| PR | Commit | What landed |
|---|---|---|
| 1 | `e5533a6` | `_send_lock` + reconnect snapshot always sends `state_sync` before `pending_review` |
| 2 | `4255ee2` | Per-iter receive-loop hardening + `_cancel_running_pipeline` helper |
| 3 | `5e47563` | Lifespan teardown cancels + awaits `pipeline_task` before `shared.shutdown` |
| 4 | `ce5a0e0` | Frontend `CANCEL_PIPELINE` sweeps stages; `send` while disconnected surfaces an error |

**Goal:** Fix real bugs in the single-client WebSocket lifecycle in `phase1-pablo`. Local-only — no auth, no heartbeat, no origin checks. Cross-PR work; each PR below is self-contained.

**Scope:**
- Backend: `phase1-pablo/src/decisionlab/server.py` (`ConnectionManager`, `websocket_endpoint`, `lifespan`).
- Frontend: `phase1-pablo/web/src/hooks/useWebSocket.ts` (reducer + `send` policy).
- Tests: new pytest cases driving `@app.websocket("/ws")` end-to-end via Starlette's `TestClient.websocket_connect`.

**Out of scope:** phase2-juan, agrex tracer, multi-client support, auth, TLS, heartbeat, origin checks. Don't add those — local-only.

**Conventions:** commit syntax `<feat/fix>[<module>]: <message>`. Auto-commit per logical chunk; never push. Run `pnpm vitest run` (web) and `pytest` (backend) before each commit.

---

## PR 1 — Test harness + `_emit_lock` + reconnect snapshot order

**Objective:** Land integration-test infrastructure for `/ws`, then fix the two highest-impact bugs together so the tests verify both.

**Bug #1 — concurrent `ws.send_json` race.** The pipeline task and the WS handler are independent coroutines. When a client reconnects mid-run, the snapshot block (`server.py:144-158`) and the next pipeline `emit()` (via `_emit_raw` at `server.py:108-112`) can interleave on the same socket. Starlette `WebSocket` is not safe for concurrent sends — frames get interleaved or `RuntimeError`. `mock_server.py` already has `_emit_lock`; the real server doesn't.

**Bug #2 — reconnect during `pending_review` skips graph snapshot.** `server.py:148-158` is `if pending_review: send pending_review ELSE send state_sync`. A client that reconnects while a review prompt is open receives the prompt with no graph behind it.

**Files:**
- `phase1-pablo/src/decisionlab/server.py` — add `self._send_lock = asyncio.Lock()` to `ConnectionManager.__init__`; wrap `ws.send_json` calls in `_emit_raw` and the snapshot block. Reorder snapshot: always send `state_sync` first, then `pending_review` if present. (run_start can stay first.)
- `phase1-pablo/tests/test_server_ws.py` — new file. Use `from starlette.testclient import TestClient`. Cases:
  - `test_reconnect_mid_run_returns_state_sync_then_resumes_events`
  - `test_reconnect_during_review_returns_snapshot_then_prompt` (covers #2)
  - `test_concurrent_emit_and_snapshot_do_not_interleave` (covers #1 — drive a fast `emit` loop while reconnecting; assert no two send_jsons overlap by instrumenting via the lock or by capturing raw frames)

**Done when:**
- 3 new pytest cases pass (`pytest phase1-pablo/tests/test_server_ws.py`)
- Existing `phase1-pablo/tests/test_server.py` still passes
- Manual smoke: live UI run, F5 mid-pipeline → graph + stage indicator both restore

---

## PR 2 — Receive loop hardening + cancel-await

**Objective:** Make the WS endpoint survive malformed input, and make `start`/`cancel` not race the previous pipeline.

**Bug #3 — receive loop only catches `WebSocketDisconnect`.** `server.py:160-186`. `receive_json()` raises `RuntimeError`/`json.JSONDecodeError` on malformed frames; `data["problem"]` raises `KeyError` on a `start` without payload. Endpoint dies, `manager.ws` is never cleared, the pipeline keeps emitting into a zombie WS.

**Bug #4 — `pipeline_task.cancel()` is fire-and-forget.** `server.py:167-175` (`start`) and `181-183` (`cancel`). Double-clicking Start cancels the old task and immediately creates a new one; the old task's tail (closing `pipeline_done` emit, trace flush) overlaps with the new task's first events on the same `manager`.

**Files:**
- `phase1-pablo/src/decisionlab/server.py` —
  - Wrap each loop iteration body in `try/except Exception`: log + send `{"type": "error", "message": ...}` + continue.
  - Validate `start` payload (`if "problem" not in data: send error frame; continue`).
  - Add `finally: manager.ws = None` outside the loop so disconnect always clears state.
  - Extract a helper `async def _cancel_running_pipeline() -> None` that does `cancel()` then `await asyncio.wait_for(asyncio.shield(task), timeout=2)` and suppresses `CancelledError` / `TimeoutError`. Call it from both the `start` and `cancel` arms.
- `phase1-pablo/tests/test_server_ws.py` — add:
  - `test_malformed_json_does_not_kill_endpoint`
  - `test_start_without_problem_returns_error_frame`
  - `test_double_start_cancels_first_pipeline_cleanly` (assert old task is `done()` before new task gets first emit)

**Done when:**
- New pytest cases pass; existing ones still pass
- Manual: send invalid frames via browser devtools, server keeps running

---

## PR 3 — Lifespan cancels pipeline on shutdown

**Objective:** Don't leak the pipeline task on Ctrl-C.

**Bug #5 — lifespan only calls `shared.shutdown()`.** `server.py:33-43`. A pipeline mid-flight on SIGTERM leaks LLM clients and may not flush `trace.jsonl`.

**Files:**
- `phase1-pablo/src/decisionlab/server.py` — in `lifespan`'s `finally`, before `shared.shutdown()`: if `manager.pipeline_task` and not done, cancel + `await asyncio.wait_for(asyncio.shield(task), timeout=5)`. Suppress `CancelledError`/`TimeoutError`. Reuse the helper from PR 2 if it's already extracted.
- `phase1-pablo/tests/test_server_ws.py` — add `test_lifespan_shutdown_cancels_running_pipeline` (boot app, start a pipeline, trigger lifespan shutdown, assert task is `done()`).

**Done when:**
- New pytest case passes; existing ones still pass
- Manual: Ctrl-C the uvicorn process during a run, no orphan log spam, trace.jsonl is closed.

---

## PR 4 — Frontend cancel sweep + send-while-disconnected policy

**Objective:** Stop the sidebar from lying after cancel, and stop silently dropping clicks during reconnect.

**Bug #6 — `CANCEL_PIPELINE` doesn't reset `stages`.** `web/src/hooks/useWebSocket.ts:80-87`. After cancel, the previously-running stage stays at `"running"` forever in the `stages` map; the sidebar shows a phantom-active stage until the next `START_PIPELINE`.

**Bug #7 — `send()` silently drops when not OPEN.** `web/src/hooks/useWebSocket.ts:376-382`. A click during the reconnect window does nothing visible.

**Files:**
- `phase1-pablo/web/src/hooks/useWebSocket.ts` —
  - In the `CANCEL_PIPELINE` reducer arm, sweep `stages`: every `"running"` → `"done"`. (Don't reset to `"pending"` — the work happened, just got interrupted.)
  - For `send()` policy, pick **one** of:
    - **Disable approach (smaller diff):** expose `connected` as the gate; UI consumers (App.tsx) already disable buttons on `!connected`. Just confirm and document. Then drop the silent `console.warn`.
    - **Buffer approach:** add a `pendingSends: ClientMessage[]` buffer (max 4 entries). On `onopen`, drain. On send-while-CLOSED, push and dispatch a "pending" UI marker.
  - Pick whichever fits the existing UX. Recommend disable approach unless you've seen real clicks-lost incidents.
- `phase1-pablo/web/src/hooks/useWebSocket.test.ts` — add cases:
  - `test_cancel_pipeline_sweeps_running_stages_to_done` (use `result.current.cancelPipeline()` after a stage)
  - If buffer approach: `test_send_while_closed_is_buffered_and_flushed_on_open`

**Done when:**
- `pnpm vitest run` passes including new cases
- `pnpm tsc -b` clean
- Manual smoke: start pipeline, cancel mid-stage → sidebar shows the stage as "done", not "running"

---

## Sequencing

PR 1 must land first (test harness is reused by PR 2 and PR 3). PR 2 and PR 3 are independent after that. PR 4 is frontend-only and parallel to all of the above.

## Verification commands

```bash
# Backend
cd phase1-pablo && uv run pytest tests/test_server.py tests/test_server_ws.py -v

# Frontend
cd phase1-pablo/web && pnpm vitest run && pnpm tsc -b

# Manual smoke (live UI)
# Terminal A: cd phase1-pablo && uv run uvicorn decisionlab.server:app --port 8000
# Terminal B: cd phase1-pablo/web && pnpm dev
# Then exercise: F5 mid-pipeline, F5 during review, double-click Start, Ctrl-C the server.
```

## What this plan deliberately does NOT do

- Does **not** add authentication, origin checks, TLS handling, or rate limiting. Local-only.
- Does **not** add ping/pong heartbeat. Local-only — TCP keepalive on loopback is sufficient.
- Does **not** touch phase2-juan. Out of scope.
- Does **not** generalize `ConnectionManager` to multi-client. Single-client is the contract.
- Does **not** refactor the agrex tracer integration. That's a separate plan (`2026-04-29-agrex-py-integration.md`).

# Phase 1 — Pipeline Replay System

**Date:** 2026-04-19
**Scope:** `phase1-pablo/` (server + web)
**Author:** Pablo Pazos Parada (design via brainstorming session)

## 1. Problem

Every pipeline run emits a stream of WebSocket events (`node_add`, `edge_add`,
`node_update`, `stage_change`, `review_request`, `agent_status`, …) that the
frontend renders as a live graph. Today those events are ephemeral: only
in-memory state survives a reconnect, and only the final `PipelineState` is
persisted to S3. There is no way to revisit a past run, and during a live run
there is no way to rewind and re-watch what a stage did before approving it at
a review checkpoint.

## 2. Goals

1. **Past-run replay.** From the idle screen, list previous runs and replay any
   of them as a faithful visual recording — no new LLM calls.
2. **In-run rewind.** At any point during a live run (especially at review
   checkpoints) the user can scrub back, step forward/back one agent action at
   a time, or replay a full stage, then jump back to live.
3. **Uniform controls.** A single timeline primitive covers live, finished, and
   past-run replay — no separate modes in the UI.

## 3. Non-goals

- Re-running the pipeline from scratch (new LLM calls). That is a separate
  feature.
- Cross-run diffing or comparison.
- Editing a past run's events.
- Persisting raw tool arguments or other data not already present in
  WebSocket events.

## 4. Architecture

```
┌──────────────────────┐      ┌──────────────────────────┐
│  Router / agents     │─emit▶│ ConnectionManager        │
│                      │      │  • broadcasts to WS      │
└──────────────────────┘      │  • appends to S3 JSONL   │
                              └──────────────────────────┘
                                        │
                           research/{run_id}/events.jsonl

┌───────────────────────────────────────────────────┐
│  REST                                              │
│   GET  /api/runs              → list (Postgres)   │
│   GET  /api/runs/{id}/events  → stream JSONL      │
└───────────────────────────────────────────────────┘

┌─ Frontend ────────────────────────────────────────┐
│  useWebSocket  (live events, unchanged)           │
│  useReplay     (new: events + cursor + controls)  │
│  Mode: "idle" | "live" | "live-finished" | "replay"│
│                                                    │
│  idle           → PastRunsList + NewRun input      │
│  live/finished  → Graph + Timeline (live cursor)   │
│  replay         → Graph + Timeline (user cursor)   │
└───────────────────────────────────────────────────┘
```

All three non-idle modes share the same `Graph` component. Graph state is
always derived from `events[0..cursor]` by folding through the existing
WebSocket reducer.

## 5. Server-side recording

### 5.1 Event format

Each persisted event is the exact payload emitted over the WebSocket, wrapped
with a monotonic sequence number and wall-clock timestamp:

```json
{"seq": 42, "ts": 1713532194812, "type": "node_add", "node": {...}}
```

`ts` is milliseconds since epoch (used to reproduce real inter-event timing in
the replay engine). `seq` is a monotonically increasing integer per run,
assigned at emit time.

### 5.2 Storage

- Key: `research/{run_id}/events.jsonl` (NDJSON format, one event per line).
- Lives alongside the existing `pipeline_state.json` in the same S3 prefix.
- Written by the server's `ConnectionManager.emit()` path.

### 5.3 `ConnectionManager` changes (`server.py`)

New fields:
- `self.seq: int = 0`
- `self.event_log: list[dict] = []` (in-memory batch buffer)

Modified `emit()`:
1. Stamp `msg` with `seq` (increment) and `ts = time.time() * 1000`.
2. Append stamped copy to `self.event_log`.
3. Send original (without `seq`/`ts`) over WS as today — the stamped values are
   only for persistence and are **not** required by the live frontend.
4. Existing state-bookkeeping branches unchanged.

### 5.4 Flush strategy

Batch-append to S3 every **50 events** or **2 s**, whichever first. Also
flush on:
- `pipeline_done` event
- `error` event
- `cancel` (explicit user cancel)
- `graph_clear` before a new run (separates runs cleanly)

Implementation: a small `EventLogger` helper owning a `deque`, a last-flush
timestamp, and an async task that flushes on a timer plus on demand.

"Append" to S3 is implemented as read-existing + put-new, since the S3
adapter does not support native append. At expected volumes (hundreds to a
few thousand events per run) this is trivial. If volumes grow, a more
efficient storage (e.g. per-batch file `events-0000.jsonl`) can be
substituted without changing the API.

### 5.5 Failure tolerance

S3 flush failure is **logged as a warning**, not propagated. A failing flush
does not break the live pipeline. The replay of the affected run may be
incomplete, which is acceptable.

### 5.6 `review_decision` event (new)

Today, the user's approve/reject is sent client → server via
`review_response`, but the server never emits a corresponding event. We add a
server emit when a review response arrives:

```json
{
  "type": "review_decision",
  "stage": "review_research",
  "approved": {"homeostatic-regulation": true, "hedonic": false}
}
```

Rationale: replays must reconstruct the dim/highlight state of output nodes,
which currently depends on `outputApprovals` held only on the live client.
Emitting `review_decision` makes approvals part of the recorded stream so
replay can fold them the same way live code does.

## 6. REST APIs

### 6.1 `GET /api/runs`

Returns runs suitable for the idle list, newest-first.

```json
[
  {
    "run_id": "6c3e…",
    "problem": "survival decision-making",
    "status": "done",
    "started_at": "2026-04-19T14:22:00Z",
    "artifact_count": 3
  }
]
```

- Source: Postgres `Run` table.
- Filter: only runs whose `status` is in `{"done", "cancelled", "failed"}` —
  runs stuck in `"running"` (e.g. crashed pre-feature) are hidden to avoid
  polluting the list.
- Ordering: `started_at DESC` (add `started_at` column if not present; fall
  back to `id` timestamp component otherwise).

### 6.2 Schema change: `Run.artifact_count`

Add a nullable `artifact_count: int | None` column to `Run`. Populated at
`pipeline_done` with `len(state.build_results)`. A small Alembic migration
ships with the feature; existing rows stay `None` and the frontend renders
`"—"` for them.

Rationale: avoid N S3 reads when listing runs.

### 6.3 `GET /api/runs/{run_id}/events`

- Reads `research/{run_id}/events.jsonl` from S3.
- Streams as `application/x-ndjson`.
- Returns `404` if the object is missing.
- Returns `409` if the run is still `running` (replay is a completed-run
  feature; live observation uses the existing WS).

## 7. Frontend — modes

App-level state adds `mode: "idle" | "live" | "live-finished" | "replay"`:

```
idle           ──click "New run"──▶ live
idle           ──click past run ──▶ replay
live           ──pipeline_done  ──▶ live-finished
live           ──click past run ──▶ (blocked, toast "cancel first")
live-finished  ──click past run ──▶ replay
live-finished  ──click "New run"──▶ live
replay         ──click "New run"──▶ live
replay         ──click past run ──▶ replay (swap events)
replay         ──click "Exit"   ──▶ idle
```

`live-finished` keeps the completed run's graph on screen and enables free
scrubbing — effectively replaying the just-finished run without leaving it.

## 8. Frontend — `useReplay` hook

New hook independent of `useWebSocket`. Signature sketch:

```ts
interface RecordedEvent {
  seq: number;
  ts: number;
  type: string;
  [rest: string]: unknown;
}

interface ReplayState {
  events: RecordedEvent[];        // fetched once per run
  cursor: number;                 // 0..events.length
  playing: boolean;
  speed: 1 | 2 | 4;
  mode: "live" | "replay";
  stageMarkers: { stage: Stage; cursor: number }[];
  reviewMarkers: { cursor: number; stage: Stage; approved: boolean }[];
}

interface ReplayActions {
  load(runId: string): Promise<void>;
  play(): void;
  pause(): void;
  seek(cursor: number): void;
  stepForward(): void;             // advance one agent-action group
  stepBack(): void;
  prevStage(): void;
  nextStage(): void;
  goLive(): void;                  // cursor = events.length
  setSpeed(s: 1 | 2 | 4): void;
}
```

### 8.1 Graph state derivation

`deriveGraphState(events.slice(0, cursor))` is a pure function that folds the
events through the existing `handleServerMessage` reducer, starting from
`INITIAL_STATE`. The live hook and the replay hook therefore share the exact
same rendering semantics — no divergence risk.

Derivation is memoised on `[events, cursor]`.

### 8.2 Playback loop

Uses a `setTimeout` chain rather than `requestAnimationFrame` so real timing
is respected:

1. `play()` sets `playing = true`, schedules the next tick.
2. Each tick advances `cursor` by 1, then waits
   `(events[cursor+1].ts - events[cursor].ts) / speed` ms.
3. Inter-event delays are **capped at 300 ms** so long idle waits (e.g.
   reviews, backend pauses) do not stall playback.
4. `pause()`, `seek()`, `stepForward()`, `stepBack()` cancel the pending
   timeout.

### 8.3 Agent-action grouping (step granularity ii)

Heuristic for grouping fine-grained events into one user-visible "step":

- A group ends when **either** of:
  - an `agent_status` event transitions an agent to `"idle"`, or
  - a `stage_change` event fires.
- `stepForward()` advances `cursor` to the index just past the next group
  boundary. `stepBack()` retreats to just past the previous boundary.

Unit-tested with fixture event streams to guarantee stability.

### 8.4 Live mode

`useWebSocket` feeds new events into `useReplay` by appending to
`events` with stamped `ts`/`seq` (client-assigned if the server message does
not carry them — live messages do not need persistent seqs). When `mode ===
"live"` and the user has not manually scrubbed, `cursor` auto-tracks
`events.length`. When the user scrubs back, `cursor` freezes and a "Return to
live" nudge appears.

## 9. Frontend — UI components

### 9.1 `<PastRunsList />` (idle)

- Absolutely positioned at the left of the bottom input area so the centred
  textarea + Play button stay visually centred.
- Approx. `w-[260px]`, height matching the textarea+button group, internal
  scroll.
- Each row:
  ```
  ┌────────────────────────────────┐
  │ survival decision-making…      │
  │ done · 3 models · Apr 18        │
  └────────────────────────────────┘
  ```
- Status pill colours match the existing style tokens (approved/rejected
  variants for `done` / `failed`; neutral for `cancelled`).
- Empty state: renders nothing; idle screen looks identical to today.
- Click row → `useReplay.load(run_id)` + switch app mode to `replay`.

### 9.2 `<Timeline />` (live / live-finished / replay)

Floating pill at bottom centre, matches existing panel style
(`bg-surface/80 backdrop-blur-xl border border-border rounded-2xl shadow-xl`).

**Expanded** (`~720px`):

```
┌───────────────────────────────────────────────────────────────┐
│ ⏮  ◀  ▶/⏸  ▶  ⏭   ●───●──◆──●──●──●   1×   00:14 / 02:47   ⏷│
└───────────────────────────────────────────────────────────────┘
```

- Left cluster: ⏮ prev-stage · ◀ step-back · ▶/⏸ play-pause · ▶ step-forward
  · ⏭ next-stage.
- Centre: scrubber spanning `[0, events.length]`. Stage markers as filled
  dots positioned at each `stage_change` cursor. Review markers as small
  amber ticks at each `review_request` cursor (hover tooltip: stage +
  approved/rejected summary). Current cursor as a diamond.
- Right cluster: speed toggle (1× / 2× / 4×), elapsed/total (from `ts`
  deltas), `⏷` collapse chevron, `⏭⏭` Live button (in live mode pins to
  latest; in replay mode jumps to end), `✕` Exit (replay only).

**Collapsed** (`~180px`):

```
┌────────────────┐
│ ▶  00:14   ⏶  │
└────────────────┘
```

- Hover/click chevron to expand.
- Collapsed state persists in `localStorage` under
  `decisionlab.timeline.collapsed`, same pattern as sidebar collapse.

### 9.3 Interaction with review bar

When a `review_request` is active, the existing floating review bar appears
at `bottom-4`. If both are open, the timeline auto-collapses to the small
pill so they don't stack. The user can expand it manually — they then stack
vertically with the timeline above the review bar.

## 10. Replay semantics for reviews

- Review markers are **passive** during playback: the cursor flies over them
  without opening the review modal.
- Dim/highlight of output nodes is reproduced by folding `review_decision`
  events into the existing `outputApprovals` state.
- No interactive approval during replay — the timeline is read-only.
- In live mode, reviews still work as today (interactive).

## 11. Testing

### Backend (pytest)

- `test_event_log_recording` — run a mock pipeline via the existing
  `mock_server`; assert `events.jsonl` exists in S3, has one line per WS
  emit, `seq` is strictly monotonic, `ts` is non-decreasing.
- `test_event_log_batching` — with a mocked S3 adapter, count `put` calls
  and assert they happen in batches (not one per event).
- `test_event_log_survives_cancel` — cancel mid-pipeline, assert a partial
  log is flushed.
- `test_runs_list_api` — seed three runs (one each of done / cancelled /
  failed / running); assert response excludes `running`, orders newest-first,
  includes `artifact_count`.
- `test_events_api_404` — request events for a run without a log → 404.
- `test_events_api_409_running` — request events for a still-running run →
  409.
- `test_review_decision_emitted` — post a `review_response` and assert a
  `review_decision` event appears in the event log.

### Frontend (vitest)

- `deriveGraphState.test.ts` — given a fixture event stream, folding to
  several cursor positions produces the expected `nodes`, `edges`,
  `stages`, `currentStage`.
- `useReplay.test.ts` — `play()` advances cursor with expected timing under
  fake timers; `stepForward()` advances exactly one group; `seek()` jumps
  directly; speed toggle scales delays; cap of 300 ms is applied.
- `stageMarkers.test.ts` — extracts markers correctly from a fixture stream.
- `timelineCollapse.test.ts` — collapse state persists to localStorage and
  restores on mount.

### Manual E2E (Playwright — existing harness)

1. **Past-run replay:** run the mock pipeline end-to-end, reload the page,
   see the run in the list, click, timeline appears with cursor at end,
   scrub back, step through, hit live.
2. **In-run rewind at review:** run a live pipeline, pause at the research
   review, manually expand the collapsed timeline, scrub back, step through
   the research stage, jump to live, approve.
3. **Mode transitions:** idle → live → live-finished → replay (by clicking
   another past run) → idle (by Exit).

## 12. File changes (summary)

### Server

- `src/decisionlab/server.py` — `ConnectionManager` adds `seq`, `event_log`,
  flush timer; `emit()` stamps and batches; new `review_decision` emit on
  review response; run-list and events endpoints added.
- `src/decisionlab/runtime/event_logger.py` (new) — batching + S3 flush.
- `shared/models.py` — `Run.artifact_count` column.
- Alembic migration — add `artifact_count`, add `started_at` if missing.

### Web

- `web/src/hooks/useReplay.ts` (new)
- `web/src/hooks/useWebSocket.ts` — minor: expose events stream to
  `useReplay`, stamp inbound messages.
- `web/src/components/PastRunsList.tsx` (new)
- `web/src/components/Timeline.tsx` (new)
- `web/src/App.tsx` — mode state machine, integrate new components,
  replace demo-only idle with list + demo.
- `web/src/types.ts` — `RecordedEvent`, `review_decision`, mode enum.

### Tests

- `tests/server/test_event_log.py` (new)
- `tests/server/test_runs_api.py` (new)
- `web/src/hooks/useReplay.test.ts` (new)
- `web/src/lib/deriveGraphState.test.ts` (new)

## 13. Open questions

- **Event-log object size ceiling.** Worst-case how many events does a run
  emit today? If we ever exceed a few MB, the read+put append strategy
  becomes wasteful and we switch to per-batch files. Not blocking.
- **Permissions.** Runs list is unauthenticated today (single-user app). If
  auth lands later, the list endpoint will need filtering by owner.
- **Retention.** No policy yet — event logs accumulate in S3 forever. Out of
  scope for this spec.

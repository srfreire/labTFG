# Trace recording

Every pipeline run produces an `agrex` JSONL trace at `s3://<bucket>/research/{run_id}/trace.jsonl`, recorded by `agrex.Tracer` in `Router._tracer`. The trace contains every graph-delta event (node_add, node_update, edge_add) the router emitted, in the canonical agrex format readable by https://agrex.ppazosp.dev. WS-extension events (`agents`, `stage_change`) are NOT in the trace — they're UI control messages, not graph deltas, so they go through `Router._send_event` directly.

To replay a finished run:

1. Download the trace from S3 (`research/{run_id}/trace.jsonl`).
2. Drop the `.jsonl` file on https://agrex.ppazosp.dev to scrub through it.

The Python tracer API (`agrex>=0.7.0`) mirrors the TypeScript sibling `@ppazosp/agrex/trace` used by the web frontend.

## Lifecycle

- `Router._init_trace(run_id)` — opens a per-run temp file, creates an `agrex.Tracer` streaming to it. Called at the top of `Router.run()`.
- `Router._finalize_trace(run_id)` — closes the tracer, uploads the file to S3, removes the local copy. Called from `Router.run()`'s `finally` block. Failures are logged but never raised.
- `Router._send_event(msg)` — forwards a single event dict to the connected WebSocket (no-op in CLI mode). Per-stage handlers call `tracer.<method>(...)` then `await self._send_event(self._tracer.events()[-1])` so the same event reaches the trace file and the live UI.

"""FastAPI WebSocket server for the DecisionLab pipeline.

Single WS endpoint at ``/ws``.  Only one concurrent client is supported —
connecting a new client disconnects the previous one.

Start with::

    uvicorn decisionlab.server:app --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

# Load .env at module import — matches the CLI entry point (cli.py:19) and
# guarantees ANTHROPIC_API_KEY is in os.environ before AsyncAnthropic() is
# instantiated inside run_pipeline. override=True so an empty-string export
# in the parent shell doesn't shadow the .env value.
load_dotenv(override=True)

from decisionlab.router import EmitFn, PipelineState, Router, Stage  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Boot shared infra once at app startup; tear down at shutdown.

    On teardown, cancel any in-flight pipeline_task before shutting down
    shared infra so the task can finalize (state.save, trace flush) while
    the LLM client / DB / S3 session are still alive. Without this the
    task is left dangling until the asyncio loop is force-closed, which
    can drop the trace.jsonl mid-write and skip the run-status update.
    """
    del app
    import shared

    await shared.init()
    try:
        yield
    finally:
        await _cancel_running_pipeline()
        await shared.shutdown()


app = FastAPI(title="DecisionLab", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Connection manager — single-client WS + pipeline state tracking
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Manages the single WebSocket connection and tracks graph state for
    reconnection. Live event stream is canonical agrex; persistence happens
    in `Router._tracer` (trace.jsonl), not here."""

    def __init__(self, storage=None) -> None:
        del storage  # legacy parameter kept for API compatibility
        self.ws: WebSocket | None = None
        self.pipeline_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.current_stage: str | None = None
        self.pending_review: dict | None = None
        self.run_id: str | None = None
        # Serializes all sends on self.ws — both pipeline emits (via
        # _emit_raw) and the reconnect snapshot in websocket_endpoint
        # contend on this. Starlette's WebSocket is not safe for concurrent
        # send, and holding the lock around bookkeeping+send keeps a
        # snapshot read from observing half-applied state.
        self._send_lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        if self.ws is not None:
            with suppress(Exception):
                await self.ws.close()
        await ws.accept()
        self.ws = ws

    async def emit(self, msg: dict) -> None:
        """Send *msg* to the WS client and update reconnection state."""
        await self._emit_raw(msg)

    async def _emit_raw(self, msg: dict) -> None:
        msg_type = msg.get("type")

        async with self._send_lock:
            # State bookkeeping under the same lock as the send so a
            # concurrent snapshot read in websocket_endpoint never observes
            # a node tracked-but-not-yet-sent (which would lead to a
            # duplicate frame after reconnect).
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

            if self.ws is not None:
                try:
                    await self.ws.send_json(msg)
                except Exception as exc:
                    logger.warning("WS send_json failed for type=%r: %s", msg_type, exc)

    async def handle_review_response(self, data: dict) -> None:
        """Dispatch the user's review decision to the waiting pipeline.

        The decision is reflected in subsequent graph deltas (node updates,
        re-run subgraphs), so no separate `review_decision` event is emitted.
        """
        from decisionlab.web_feedback import handle_review_response as _dispatch

        _dispatch(data["stage"], data["data"])

    def reset(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.current_stage = None
        self.pending_review = None
        self.run_id = None


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


async def _cancel_running_pipeline() -> None:
    """Cancel ``manager.pipeline_task`` and wait for it to wind down.

    Used by both the ``start`` and ``cancel`` arms of the WS receive loop
    (and by the lifespan shutdown in PR 3). Without the await, the new
    task's first emits race the old task's cancellation tail (closing
    ``pipeline_done``, ``state.save()``, trace flush) on the same
    ``ConnectionManager``.

    Suppresses ``CancelledError`` / ``TimeoutError`` so the caller can
    proceed; logs anything else the task raised during unwind.
    """
    task = manager.pipeline_task
    if task is None or task.done():
        return
    task.cancel()
    try:
        # ``shield`` lets the task finish unwinding even if the caller is
        # itself cancelled (e.g. WS disconnects mid-cancel).
        await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
    except (TimeoutError, asyncio.CancelledError):
        pass
    except Exception:
        logger.exception("Pipeline task raised during cancellation")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)

    # Reconnection: re-emit pending state so the frontend can catch up.
    # The snapshot runs under manager._send_lock so an in-flight pipeline
    # emit can't interleave frames or update bookkeeping mid-snapshot.
    if manager.pipeline_task and not manager.pipeline_task.done():
        async with manager._send_lock:
            if manager.run_id:
                await ws.send_json({"type": "run_start", "run_id": manager.run_id})
            # Always send the graph snapshot before the review prompt — the
            # UI needs both to render the prompt against the right context.
            await ws.send_json(
                {
                    "type": "state_sync",
                    "nodes": list(manager.nodes),
                    "edges": list(manager.edges),
                    "stage": manager.current_stage,
                }
            )
            if manager.pending_review:
                await ws.send_json(manager.pending_review)

    try:
        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                # Malformed JSON, decoding error, anything that isn't a clean
                # disconnect — keep the connection alive and inform the client.
                logger.warning("WS receive failed: %s", exc)
                try:
                    await manager.emit(
                        {"type": "error", "message": f"invalid frame: {exc}"}
                    )
                except Exception:
                    logger.debug("Failed to send error frame after bad receive")
                continue

            msg_type = data.get("type") if isinstance(data, dict) else None

            try:
                if msg_type == "start":
                    problem = data.get("problem")
                    if not isinstance(problem, str) or not problem.strip():
                        await manager.emit(
                            {
                                "type": "error",
                                "message": "start requires a non-empty 'problem' field",
                            }
                        )
                        continue
                    await _cancel_running_pipeline()
                    manager.reset()
                    until_stage: str | None = data.get("until_stage")
                    manager.pipeline_task = asyncio.create_task(
                        run_pipeline(problem, manager.emit, until_stage=until_stage)
                    )

                elif msg_type == "review_response":
                    await manager.handle_review_response(data)

                elif msg_type == "cancel":
                    await _cancel_running_pipeline()
                    manager.reset()
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                logger.exception("Error handling WS message type=%r", msg_type)
                try:
                    await manager.emit({"type": "error", "message": str(exc)})
                except Exception:
                    logger.debug("Failed to send error frame after handler error")

    except WebSocketDisconnect:
        pass
    finally:
        manager.ws = None


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


async def run_pipeline(
    problem: str,
    emit: EmitFn,
    until_stage: str | None = None,
) -> None:
    """Run the full pipeline, emitting events via *emit*.

    *until_stage* is the optional --until X equivalent: when set to a work
    stage value (research/formalize/reason/build), the pipeline terminates
    after the matching review stage. Invalid values are dropped silently with
    a warning so a malformed WS payload doesn't crash the runner.
    """
    import uuid

    from anthropic import AsyncAnthropic

    import shared
    from decisionlab.adapters import default_search_chain
    from shared.models import Run

    stop_after: Stage | None = None
    if until_stage is not None:
        valid = {
            Stage.RESEARCH.value: Stage.RESEARCH,
            Stage.FORMALIZE.value: Stage.FORMALIZE,
            Stage.REASON.value: Stage.REASON,
            Stage.BUILD.value: Stage.BUILD,
        }
        if until_stage in valid:
            stop_after = valid[until_stage]
        else:
            logger.warning(
                "Ignoring invalid until_stage=%r — must be one of %s",
                until_stage,
                ", ".join(valid),
            )

    try:
        client = AsyncAnthropic()
        search = default_search_chain()

        run_id = str(uuid.uuid4())
        await emit({"type": "run_start", "run_id": run_id})
        async with shared.db.get_session() as session:
            db_run = Run(
                id=uuid.UUID(run_id),
                problem_description=problem,
                status="running",
                s3_prefix=f"research/{run_id}",
            )
            session.add(db_run)
            await session.commit()

        slug = problem.lower().replace(" ", "-")[:50]
        reports_dir = Path(f"reports/{date.today().isoformat()}-{slug}")
        reports_dir.mkdir(parents=True, exist_ok=True)

        state = PipelineState(
            stage=Stage.CLASSIFY_UMBRELLA,
            problem=problem,
            reports_dir=reports_dir,
            run_id=run_id,
        )

        from decisionlab.feedback_port import WebFeedback

        router = Router(
            client=client,
            state=state,
            search=search,
            project_root=Path.cwd(),
            emit=emit,
            stop_after=stop_after,
            feedback=WebFeedback(emit),
        )

        try:
            await router.run()
            # Update Run status on success
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
        except asyncio.CancelledError:
            await state.save()
            try:
                async with shared.db.get_session() as session:
                    from sqlalchemy import update

                    await session.execute(
                        update(Run)
                        .where(Run.id == uuid.UUID(run_id))
                        .values(status="cancelled")
                    )
                    await session.commit()
            except Exception:
                logger.debug("Could not mark run as cancelled")
            raise
        except Exception as exc:
            logger.exception("Pipeline failed")
            try:
                async with shared.db.get_session() as session:
                    from sqlalchemy import update

                    await session.execute(
                        update(Run)
                        .where(Run.id == uuid.UUID(run_id))
                        .values(status="failed")
                    )
                    await session.commit()
            except Exception:
                logger.debug("Could not mark run as failed")
            await emit({"type": "error", "message": str(exc)})
    finally:
        from decisionlab.runtime.usage import log_summary as log_usage_summary

        log_usage_summary()


# ---------------------------------------------------------------------------
# KG snapshot endpoint — full graph (active relations only)
# ---------------------------------------------------------------------------


@app.get("/api/kg/snapshot")
async def kg_snapshot(run_id: str | None = None) -> dict:
    """Return all nodes and active (non-superseded) relations.

    Each node carries ``run_count`` (cumulative MERGEs that have touched it)
    and ``last_run_at`` (most recent MERGE timestamp), which replaced the
    old per-node ``run_ids`` array (memory-refactor P0-004). When ``run_id``
    is supplied, the response also contains ``current_run_node_ids`` — the
    Neo4j elementIds of nodes the run has touched, computed by joining
    against the Postgres ``node_run_observations`` table; the frontend uses
    it to highlight new-this-run nodes.
    """
    import shared

    if shared.kg is None:
        raise HTTPException(status_code=503, detail="Knowledge graph unavailable")

    nodes_raw = await shared.kg.query(
        "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, "
        "properties(n) AS props"
    )
    rels_raw = await shared.kg.query(
        "MATCH (a)-[r]->(b) WHERE r.valid_to IS NULL "
        "RETURN elementId(r) AS id, elementId(a) AS source, "
        "elementId(b) AS target, type(r) AS type, properties(r) AS props"
    )

    nodes = []
    label_key_to_id: dict[tuple[str, str], str] = {}
    for n in nodes_raw:
        props = n["props"] or {}
        label = n["labels"][0] if n["labels"] else "Node"
        # Display label: prefer 'name', fall back to the natural key value.
        display = (
            props.get("name")
            or props.get("slug")
            or props.get("id")
            or props.get("latex")
            or props.get("doi")
            or props.get("formulation_id")
            or label
        )
        # Index every plausible natural-key property — `kg_writer` may have
        # picked any of these, and `node_run_observations` stores the value
        # used at write time. Enumerating them all keeps the lookup
        # in sync without coupling to `_resolve_natural_key`'s precedence.
        for key_prop in (
            "slug",
            "id",
            "doi",
            "name",
            "title",
            "latex",
            "url",
            "formulation_id",
            "_synthetic_id",
        ):
            val = props.get(key_prop)
            if val is not None:
                label_key_to_id.setdefault((label, str(val)), n["id"])
        nodes.append(
            {
                "id": n["id"],
                "label": label,
                "display": str(display)[:60],
                "run_count": props.get("run_count", 0),
                "last_run_at": props.get("last_run_at"),
                "properties": props,
            }
        )

    relations = []
    for r in rels_raw:
        props = r["props"] or {}
        relations.append(
            {
                "id": r["id"],
                "source": r["source"],
                "target": r["target"],
                "type": r["type"],
                "run_id": props.get("run_id"),
                "properties": props,
            }
        )

    current_run_node_ids = await _resolve_current_run_node_ids(run_id, label_key_to_id)

    return {
        "nodes": nodes,
        "relations": relations,
        "current_run_node_ids": current_run_node_ids,
    }


async def _resolve_current_run_node_ids(
    run_id: str | None, label_key_to_id: dict[tuple[str, str], str]
) -> list[str]:
    """Map (label, key_value) observations for ``run_id`` back to Neo4j elementIds.

    Returns an empty list when no ``run_id`` is provided, the run_id isn't
    a UUID (e.g. the seed run), or Postgres is unavailable. The frontend
    treats the empty case as "no highlighting needed".
    """
    if not run_id:
        return []
    try:
        import uuid as _uuid

        parsed = _uuid.UUID(run_id)
    except ValueError:
        return []

    import shared

    if shared.db is None:
        return []

    from sqlalchemy import text as sql_text

    try:
        async with shared.db.get_session() as session:
            result = await session.execute(
                sql_text(
                    "SELECT label, key_value FROM node_run_observations "
                    "WHERE run_id = :run_id"
                ),
                {"run_id": parsed},
            )
            rows = result.all()
    except Exception:
        logger.warning(
            "kg_snapshot: node_run_observations lookup failed", exc_info=True
        )
        return []

    ids: list[str] = []
    for row in rows:
        node_id = label_key_to_id.get((row.label, row.key_value))
        if node_id is not None:
            ids.append(node_id)
    return ids


@app.get("/api/runs")
async def list_runs() -> list[dict]:
    """Return terminal runs newest-first for the idle-screen past-runs list."""
    from sqlalchemy import select

    import shared
    from shared.models import Run

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
            "final_stage": r.final_stage,
            "memory_results": r.memory_results,
        }
        for r in rows
    ]


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

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Trace not found") from None

    async with shared.db.get_session() as session:
        result = await session.execute(select(Run.status).where(Run.id == run_uuid))
        row = result.first()
    if row is not None and row[0] == "running":
        raise HTTPException(status_code=409, detail="Run still in progress")

    key = f"research/{run_id}/trace.jsonl"
    if not await shared.storage.exists(key):
        raise HTTPException(status_code=404, detail="Trace not found")
    body = await shared.storage.get_text(key)
    return PlainTextResponse(body, media_type="application/x-ndjson")

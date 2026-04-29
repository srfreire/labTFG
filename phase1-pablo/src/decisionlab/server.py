"""FastAPI WebSocket server for the DecisionLab pipeline.

Single WS endpoint at ``/ws``.  Only one concurrent client is supported —
connecting a new client disconnects the previous one.

Start with::

    uvicorn decisionlab.server:app --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
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
    """Boot shared infra once at app startup; tear down at shutdown."""
    del app
    import shared

    await shared.init()
    try:
        yield
    finally:
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

    async def connect(self, ws: WebSocket) -> None:
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
        await ws.accept()
        self.ws = ws

    async def emit(self, msg: dict) -> None:
        """Send *msg* to the WS client and update reconnection state."""
        await self._emit_raw(msg)

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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)

    # Reconnection: re-emit pending state so the frontend can catch up
    if manager.pipeline_task and not manager.pipeline_task.done():
        if manager.run_id:
            await ws.send_json({"type": "run_start", "run_id": manager.run_id})
        if manager.pending_review:
            await ws.send_json(manager.pending_review)
        else:
            await ws.send_json(
                {
                    "type": "state_sync",
                    "nodes": manager.nodes,
                    "edges": manager.edges,
                    "stage": manager.current_stage,
                }
            )

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "start":
                # Cancel any running pipeline
                if manager.pipeline_task and not manager.pipeline_task.done():
                    manager.pipeline_task.cancel()
                manager.reset()

                problem: str = data["problem"]
                until_stage: str | None = data.get("until_stage")
                manager.pipeline_task = asyncio.create_task(
                    run_pipeline(problem, manager.emit, until_stage=until_stage)
                )

            elif msg_type == "review_response":
                await manager.handle_review_response(data)

            elif msg_type == "cancel":
                if manager.pipeline_task and not manager.pipeline_task.done():
                    manager.pipeline_task.cancel()
                    manager.reset()

    except WebSocketDisconnect:
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
    from decisionlab.adapters.duckduckgo import DuckDuckGoAdapter
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
        search = DuckDuckGoAdapter()

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
            stage=Stage.RESEARCH,
            problem=problem,
            reports_dir=reports_dir,
            run_id=run_id,
        )

        router = Router(
            client=client,
            state=state,
            search=search,
            project_root=Path.cwd(),
            emit=emit,
            stop_after=stop_after,
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
async def kg_snapshot() -> dict:
    """Return all nodes and active (non-superseded) relations.

    Frontend uses ``run_ids`` / ``run_id`` to distinguish nodes/edges created
    during the current run.
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
        nodes.append(
            {
                "id": n["id"],
                "label": label,
                "display": str(display)[:60],
                "run_ids": props.get("run_ids", []),
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

    return {"nodes": nodes, "relations": relations}


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
        result = await session.execute(
            select(Run.status).where(Run.id == run_uuid)
        )
        row = result.first()
    if row is not None and row[0] == "running":
        raise HTTPException(status_code=409, detail="Run still in progress")

    key = f"research/{run_id}/trace.jsonl"
    if not await shared.storage.exists(key):
        raise HTTPException(status_code=404, detail="Trace not found")
    body = await shared.storage.get_text(key)
    return PlainTextResponse(body, media_type="application/x-ndjson")

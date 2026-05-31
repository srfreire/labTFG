"""
FastAPI backend — WebSocket API for the Orchestrator.

The web UI connects via WebSocket to /ws and sends chat messages.
The server creates an Orchestrator per connection and streams back:
  - Agent status updates (working/done/idle)
  - Chat responses with data cards (environment spec, simulation summary)
  - Tracker and Analyst results
  - Replay data for the simulation grid animation
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy import text as sql_text

from shared.models import PipelineMemory
from shared.services import Services, init_services, shutdown_services
from simlab.knowledge import build_writer_from_services
from simlab.orchestrator import Orchestrator

load_dotenv()

logger = logging.getLogger(__name__)

# Set by ``lifespan`` and read by ``websocket_chat`` to construct the
# per-connection Orchestrator with explicit infra wiring.
_services: Services | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _services
    services = await init_services()
    # Phase 2 simulation memory writer — opt-in via ENABLE_KNOWLEDGE_WRITE.
    from shared.settings import load_settings

    settings = load_settings()
    if settings.ENABLE_KNOWLEDGE_WRITE:
        writer = build_writer_from_services(services)
        if writer is not None:
            services = replace(services, sim_memory_writer=writer)
    _services = services
    try:
        yield
    finally:
        if _services is not None:
            await shutdown_services(_services)
        _services = None


app = FastAPI(title="DecisionLab API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Agent status tracking — used by the web UI sidebar
# ---------------------------------------------------------------------------

# Single source of truth for agent names, colors, and which state key indicates "done"
AGENTS = [
    {"name": "Architect", "color": "#4ade80", "state_key": "spec"},
    {"name": "Tracker", "color": "#fbbf24", "state_key": "tracker_output"},
    {"name": "Analyst", "color": "#a78bfa", "state_key": "analyst_output"},
    {"name": "Reporter", "color": "#f472b6", "state_key": "pdf_path"},
]

# Colors for simulation agents (assigned round-robin by index).
# Derived from AGENTS for the first 4 slots, then extended for additional
# in-grid agents beyond the four pipeline roles.
SIM_AGENT_COLORS = [a["color"] for a in AGENTS] + ["#38bdf8", "#fb923c"]

# Maps orchestrator tool names to agent names for real-time status updates
TOOL_AGENT_MAP = {
    "create_environment": "Architect",
    "observe_simulation": "Tracker",
    "analyze_results": "Analyst",
    "generate_report": "Reporter",
}


def _build_agent_states(orch_state: dict | None = None) -> list[dict]:
    """Build the agent state list from orchestrator state."""
    return [
        {
            "name": a["name"],
            "status": "done"
            if orch_state and orch_state.get(a["state_key"])
            else "idle",
            "color": a["color"],
        }
        for a in AGENTS
    ]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Knowledge Graph endpoints (knowledge P7)
# ---------------------------------------------------------------------------

_NODE_KEY_PROPS = (
    "slug",
    "id",
    "doi",
    "name",
    "title",
    "latex",
    "formulation_id",
    "_synthetic_id",
)

_GRAPH_SCOPES: dict[str, tuple[str, ...]] = {
    # The drawer's default view is for orientation, not data mining. Keeping this
    # server-side avoids shipping equations/variables/parameters to ReactFlow.
    "overview": ("Paradigm", "Model", "Formulation", "Postulate"),
}


@app.get("/api/knowledge/graph")
async def knowledge_graph(
    run_id: str | None = None,
    label: str | None = None,
    scope: str | None = None,
) -> dict:
    """KG snapshot for the Phase 2 frontend KnowledgePanel.

    Returns nodes + edges from Neo4j. When ``run_id`` is provided, the
    response also carries ``current_run_node_ids`` — Neo4j elementIds of
    nodes touched by that run (resolved via the Postgres
    ``node_run_observations`` table). The ``label`` filter restricts the
    response to nodes whose primary Cypher label matches.

    503 when Neo4j is unavailable or the underlying query raises.
    """
    if _services is None or _services.kg is None:
        raise HTTPException(status_code=503, detail="Knowledge graph unavailable")

    scope_labels = _GRAPH_SCOPES.get(scope or "")
    if label:
        scope_labels = (label,)

    node_query = (
        "MATCH (n) WHERE any(label IN labels(n) WHERE label IN $labels) "
        "RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props"
        if scope_labels
        else "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, "
        "properties(n) AS props"
    )
    node_params = {"labels": list(scope_labels)} if scope_labels else None
    edge_query = (
        "MATCH (a)-[r]->(b) "
        "WHERE any(label IN labels(a) WHERE label IN $labels) "
        "AND any(label IN labels(b) WHERE label IN $labels) "
        "RETURN elementId(r) AS id, elementId(a) AS source, "
        "elementId(b) AS target, type(r) AS type, properties(r) AS props"
        if scope_labels
        else "MATCH (a)-[r]->(b) "
        "RETURN elementId(r) AS id, elementId(a) AS source, "
        "elementId(b) AS target, type(r) AS type, properties(r) AS props"
    )

    try:
        nodes_raw, edges_raw = await asyncio.gather(
            _services.kg.query(node_query, node_params),
            _services.kg.query(edge_query, node_params),
        )
    except Exception:
        logger.warning("knowledge_graph: Neo4j query failed", exc_info=True)
        raise HTTPException(status_code=503, detail="Knowledge graph query failed")

    nodes: list[dict] = []
    label_key_to_id: dict[tuple[str, str], str] = {}
    for n in nodes_raw:
        props = n["props"] or {}
        node_label = n["labels"][0] if n["labels"] else "Node"
        if label and node_label != label:
            continue
        for key_prop in _NODE_KEY_PROPS:
            val = props.get(key_prop)
            if val is not None:
                label_key_to_id.setdefault((node_label, str(val)), n["id"])
        nodes.append({"id": n["id"], "label": node_label, "props": props})

    kept_ids = {n["id"] for n in nodes}
    edges = [
        {
            "id": r["id"],
            "source": r["source"],
            "target": r["target"],
            "type": r["type"],
            "props": r["props"] or {},
        }
        for r in edges_raw
        if r["source"] in kept_ids and r["target"] in kept_ids
    ]

    current_run_node_ids = await _resolve_current_run_node_ids(
        run_id, label_key_to_id
    )

    return {
        "nodes": nodes,
        "edges": edges,
        "current_run_node_ids": current_run_node_ids,
    }


_MEMORIES_MAX_PAGE_SIZE = 200
_MEMORIES_DEFAULT_PAGE_SIZE = 50


@app.get("/api/knowledge/memories")
async def knowledge_memories(
    namespace: str | None = None,
    run_id: str | None = None,
    since: str | None = None,
    page: int = 1,
    page_size: int = _MEMORIES_DEFAULT_PAGE_SIZE,
) -> dict:
    """Browse the Phase 1 ``pipeline_memories`` table for the KnowledgePanel.

    Filters: ``namespace`` (paradigm/formulation/model/meta),
    ``run_id`` (UUID), ``since`` (ISO 8601 timestamp).
    Pagination: ``page`` (1-based), ``page_size`` (default 50, max 200).
    Sort: newest first by ``created_at``.

    503 when Postgres is unreachable.
    """
    if _services is None or _services.db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    page = max(1, page)
    page_size = max(1, min(page_size, _MEMORIES_MAX_PAGE_SIZE))

    parsed_run_id: uuid.UUID | None = None
    if run_id:
        try:
            parsed_run_id = uuid.UUID(run_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid run_id (expected UUID): {exc}"
            ) from exc

    parsed_since: datetime | None = None
    if since:
        try:
            parsed_since = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid since (expected ISO 8601): {exc}",
            ) from exc

    filters = []
    if namespace:
        filters.append(PipelineMemory.namespace == namespace)
    if parsed_run_id is not None:
        filters.append(PipelineMemory.run_id == parsed_run_id)
    if parsed_since is not None:
        filters.append(PipelineMemory.created_at >= parsed_since)

    items_stmt = (
        select(PipelineMemory)
        .where(*filters)
        .order_by(PipelineMemory.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    count_stmt = select(func.count()).select_from(PipelineMemory).where(*filters)

    try:
        async with _services.db.get_session() as session:
            rows = (await session.execute(items_stmt)).scalars().all()
            total = (await session.execute(count_stmt)).scalar_one()
    except Exception:
        logger.warning("knowledge_memories: query failed", exc_info=True)
        raise HTTPException(status_code=503, detail="Memories query failed")

    items = [
        {
            "id": str(m.id),
            "content": m.content,
            "namespace": m.namespace,
            "run_id": str(m.run_id),
            "memory_type": m.memory_type,
            "source_stage": m.source_stage,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]

    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


_PROVENANCE_MAX_DEPTH = 4
_PROVENANCE_PATH_LIMIT = 25


@app.get("/api/knowledge/provenance/{node_id}")
async def knowledge_provenance(node_id: str) -> dict:
    """Trail from ``node_id`` toward source ``Paper`` nodes.

    Walks undirected edges (SUPPORTS / DERIVES_FROM / AUTHORED / CITES /
    IMPLEMENTS / ...) up to depth 4 toward any ``Paper`` node and returns
    the longest such trail — the most informative provenance chain.
    Undirected because Papers carry incoming ``SUPPORTS`` edges
    (``Paper -[:SUPPORTS]-> Postulate``), so walking strict outgoing from
    a Postulate would never reach its supporting Paper. Empty ``trail``
    is valid: the node and any reachable Paper sit in disconnected KG
    components.

    404 when the node does not exist. 503 when Neo4j is unavailable or
    the underlying query raises.
    """
    if _services is None or _services.kg is None:
        raise HTTPException(status_code=503, detail="Knowledge graph unavailable")

    try:
        rows = await _services.kg.query(
            "MATCH (n) WHERE elementId(n) = $id "
            f"OPTIONAL MATCH path = (n)-[*1..{_PROVENANCE_MAX_DEPTH}]-(:Paper) "
            "WITH n, path ORDER BY size(coalesce(relationships(path), [])) DESC "
            f"LIMIT {_PROVENANCE_PATH_LIMIT} "
            "WITH n, [p IN collect(path) WHERE p IS NOT NULL] AS paths "
            "RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props, "
            "[p IN paths[..1] | "
            "[r IN relationships(p) | "
            "{id: elementId(r), type: type(r), props: properties(r)}]] AS edge_lists, "
            "[p IN paths[..1] | "
            "[m IN nodes(p)[1..] | "
            "{id: elementId(m), labels: labels(m), props: properties(m)}]] AS node_lists",
            {"id": node_id},
        )
    except Exception:
        logger.warning("knowledge_provenance: query failed", exc_info=True)
        raise HTTPException(status_code=503, detail="Knowledge graph query failed")

    if not rows:
        raise HTTPException(status_code=404, detail="Node not found")

    row = rows[0]
    node = {
        "id": row["id"],
        "label": (row["labels"] or ["Node"])[0],
        "props": row["props"] or {},
    }
    edges = row["edge_lists"][0] if row["edge_lists"] else []
    path_nodes = row["node_lists"][0] if row["node_lists"] else []

    trail = [
        {
            "edge": {
                "id": edge["id"],
                "type": edge["type"],
                "props": edge["props"] or {},
            },
            "node": {
                "id": m["id"],
                "label": (m["labels"] or ["Node"])[0],
                "props": m["props"] or {},
            },
        }
        for edge, m in zip(edges, path_nodes, strict=True)
    ]

    return {"node": node, "trail": trail}


async def _resolve_current_run_node_ids(
    run_id: str | None,
    label_key_to_id: dict[tuple[str, str], str],
) -> list[str]:
    """Resolve elementIds of nodes touched by ``run_id`` via Postgres.

    Empty list when no ``run_id`` is given, the value is not a UUID, or
    Postgres is unreachable — the frontend treats that as "no highlight".
    """
    if not run_id or _services is None or _services.db is None:
        return []
    try:
        parsed = uuid.UUID(run_id)
    except ValueError:
        return []

    try:
        async with _services.db.get_session() as session:
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
            "knowledge_graph: node_run_observations lookup failed", exc_info=True
        )
        return []

    ids: list[str] = []
    for row in rows:
        node_id = label_key_to_id.get((row.label, row.key_value))
        if node_id is not None:
            ids.append(node_id)
    return ids


@app.websocket("/ws")
async def websocket_chat(ws: WebSocket):
    """Main WebSocket endpoint — one Orchestrator per connection."""
    await ws.accept()

    client = anthropic.AsyncAnthropic(timeout=120.0)
    if _services is None:
        await ws.close(code=1011, reason="services not initialised")
        return
    orch = Orchestrator(client=client, services=_services)

    # Once the client disconnects, every subsequent ws.send_json raises and
    # cascades through the orchestrator's tool loop as a barrage of tracebacks.
    # Flip this flag in the disconnect handler and have all sends become no-ops.
    ws_alive = {"v": True}

    async def safe_send(payload: dict) -> None:
        if not ws_alive["v"]:
            return
        try:
            await ws.send_json(payload)
        except (WebSocketDisconnect, RuntimeError):
            ws_alive["v"] = False

    # Send initial agent states + color palette to the UI
    await safe_send(
        {
            "type": "agents",
            "agents": _build_agent_states(),
            "pipeline": [],
            "simColors": SIM_AGENT_COLORS,
        }
    )

    # Wire up internal tool call notifications
    async def _on_agent_tool(agent_name: str, tool_name: str):
        await safe_send(
            {"type": "agent_tool", "agent": agent_name, "tool": tool_name}
        )

    orch.on_agent_tool_call = _on_agent_tool

    # Monkey-patch orchestrator tools to emit real-time agent status via WebSocket
    original_build = orch._build_tools

    # --- Intermediate card builders (one per pipeline step) ---

    def _env_card(state: dict) -> dict | None:
        spec = state.get("spec")
        if not spec:
            return None
        resources = ", ".join(f"{r['type']} ×{r['count']}" for r in spec["resources"])
        data: dict[str, str] = {
            "Grid": f"{spec['grid']['width']} × {spec['grid']['height']}",
            "Acciones posibles": ", ".join(
                a["name"] if isinstance(a, dict) else str(a)
                for a in spec["actions"]
            ),
            "Recursos": resources,
        }
        # Seed and step count only known after run_simulation completes;
        # render them once they land in state so the sidebar env panel can
        # surface reproducibility info without a separate websocket event.
        if state.get("seed") is not None:
            data["Seed"] = str(state["seed"])
        replay = state.get("replay")
        if replay:
            data["Pasos ejecutados"] = str(replay.get("total_steps", "—"))
        return {
            "type": "message",
            "from": "orchestrator",
            "text": f"El **Architect** ha diseñado el entorno de simulación: un grid {spec['grid']['width']}×{spec['grid']['height']} con {resources}. Ahora voy a buscar los modelos disponibles y lanzar la simulación.",
            "card": {
                "title": "Environment Spec",
                "data": data,
            },
        }

    def _sim_card(state: dict) -> dict | None:
        replay = state.get("replay")
        if not replay:
            return None
        n_agents = len(replay["frames"][0]["agents"]) if replay["frames"] else 0
        return {
            "type": "message",
            "from": "orchestrator",
            "text": f"Simulación completada: **{n_agents} agentes** durante **{replay['total_steps']} pasos**. Puedes explorar el replay paso a paso. Ahora el Tracker va a observar qué pasó.",
            "replay": replay,
        }

    def _tracker_card(state: dict) -> dict | None:
        raw = state.get("tracker_output")
        if not raw:
            return None
        try:
            tracker = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if "trajectories" not in tracker:
            return None
        n_traj = len(tracker["trajectories"])
        episodes = tracker.get("episodes", [])
        ep_summary = ""
        if episodes:
            ep_lines = [
                f"- **{ep.get('agent', '')}**: {ep.get('description', ep.get('type', ''))}"
                if ep.get("agent")
                else f"- {ep.get('description', ep.get('type', ''))}"
                for ep in episodes[:5]
            ]
            ep_summary = "\n\nEpisodios detectados:\n" + "\n".join(ep_lines)
        return {
            "type": "message",
            "from": "orchestrator",
            "text": f"El **Tracker** ha registrado las trayectorias de **{n_traj} agentes**.{ep_summary}\n\nAhora el Analyst va a buscar patrones.",
            "tracker": tracker,
        }

    def _analyst_card(state: dict) -> dict | None:
        raw = state.get("analyst_output")
        if not raw:
            return None
        try:
            analyst = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if "patterns" not in analyst:
            return None
        n_pat = len(analyst["patterns"])
        n_comp = len(analyst.get("comparisons", []))
        charts = state.get("_last_charts") or []
        chart_text = f" y generado **{len(charts)} gráficas**" if charts else ""
        msg: dict = {
            "type": "message",
            "from": "orchestrator",
            "text": f"El **Analyst** ha encontrado **{n_pat} patrones**, realizado **{n_comp} comparaciones**{chart_text}.",
            "analyst": analyst,
        }
        if charts:
            msg["charts"] = charts
        return msg

    def _reporter_card(state: dict) -> dict | None:
        paths = state.get("pdf_paths")
        if not paths:
            return None
        if len(paths) == 1:
            text = f"El **Reporter** ha generado el informe PDF: `{paths[0]}`."
        else:
            pdf_list = "\n".join(f"- `{p}`" for p in paths)
            text = f"El **Reporter** ha generado **{len(paths)} informes** PDF:\n{pdf_list}"
        return {"type": "message", "from": "orchestrator", "text": text}

    _CARD_BUILDERS = {
        "create_environment": _env_card,
        "run_simulation": _sim_card,
        "observe_simulation": _tracker_card,
        "analyze_results": _analyst_card,
        "generate_report": _reporter_card,
    }

    # Per-session signatures of env cards already emitted. ONLY env cards
    # are deduped here — the LLM tends to re-invoke create_environment under
    # the same spec across turns, and emitting the same env card 3 times in
    # the chat was the user-visible symptom. Sim/tracker/analyst/reporter
    # cards are intentionally NOT deduped: they carry per-run artifacts
    # (replay frames, trajectories, patterns) and must fire on every pipeline
    # iteration. A previous version used msg.get("card") in the sig, which
    # collapsed to "null" for those four tools and silently suppressed every
    # second-run card in the same session.
    sent_env_card_sigs: set[str] = set()

    async def _send_intermediate_card(tool_name: str):
        """Send data cards to frontend as each pipeline step completes."""
        builder = _CARD_BUILDERS.get(tool_name)
        if not builder:
            return
        msg = builder(orch._state)
        if not msg:
            return
        if tool_name == "create_environment":
            # Dedup on the stable spec-derived fields only — Seed and
            # "Pasos ejecutados" arrive AFTER run_simulation and would
            # otherwise produce a fresh sig on the post-sim re-call,
            # double-emitting the env card in the chat.
            card_data = (msg.get("card") or {}).get("data") or {}
            stable_data = {
                k: v
                for k, v in card_data.items()
                if k not in ("Seed", "Pasos ejecutados")
            }
            sig = json.dumps(stable_data, sort_keys=True, default=str)
            if sig in sent_env_card_sigs:
                return
            sent_env_card_sigs.add(sig)
        await safe_send(msg)

    def patched_build(settings=None):
        tools, registry = original_build(settings)
        wrapped = {}
        for tool_name, fn in registry.items():
            agent_name = TOOL_AGENT_MAP.get(tool_name)
            if agent_name:

                async def _wrapper(params, _tool=tool_name, _agent=agent_name, _fn=fn):
                    await safe_send(
                        {"type": "agent_status", "agent": _agent, "status": "working"}
                    )
                    try:
                        result = await _fn(params)
                    except Exception:
                        await safe_send(
                            {"type": "agent_status", "agent": _agent, "status": "idle"}
                        )
                        raise
                    await safe_send(
                        {"type": "agent_status", "agent": _agent, "status": "done"}
                    )
                    await _send_intermediate_card(_tool)
                    return result

                wrapped[tool_name] = _wrapper
            else:
                # Non-mapped tools (run_simulation, list_available_models,
                # read_predictions, list_experiments, query_experiments,
                # get_tracker_detail, get_analyst_detail, …) all share this
                # wrapper. We only want to refresh the sidebar env card
                # AFTER a sim has actually run — otherwise every catalogue
                # query would re-push it for no reason.
                async def _sim_wrapper(params, _tool=tool_name, _fn=fn):
                    result = await _fn(params)
                    await _send_intermediate_card(_tool)
                    if _tool == "run_simulation":
                        refreshed = _env_card(orch._state)
                        if refreshed:
                            await safe_send(
                                {
                                    "type": "env_card_update",
                                    "card": refreshed["card"],
                                }
                            )
                    return result

                wrapped[tool_name] = _sim_wrapper
        return tools, wrapped

    orch._build_tools = patched_build

    # --- Chat loop ---
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            user_text = msg.get("message", "")

            if not user_text.strip():
                continue

            await safe_send({"type": "status", "status": "thinking"})

            try:
                response = await orch.chat(user_text)
                state = orch._state

                # Send updated agent states
                agents_state = _build_agent_states(state)
                pipeline = []
                for key, step in [
                    ("spec", "arch"),
                    ("events", "sim"),
                    ("tracker_output", "track"),
                    ("analyst_output", "anal"),
                    ("pdf_path", "repo"),
                ]:
                    if state.get(key):
                        pipeline.append({"step": step, "status": "done"})

                await safe_send(
                    {"type": "agents", "agents": agents_state, "pipeline": pipeline}
                )

                # Send the orchestrator's final text response
                # Data cards were already sent in streaming via _send_intermediate_card
                if response.strip():
                    await safe_send(
                        {
                            "type": "message",
                            "from": "orchestrator",
                            "text": response,
                        }
                    )
                await safe_send({"type": "status", "status": "done"})

            except WebSocketDisconnect:
                ws_alive["v"] = False
                raise
            except Exception as e:
                logger.error("Orchestrator error: %s", e, exc_info=True)
                await safe_send({"type": "error", "text": str(e)})
                await safe_send({"type": "status", "status": "done"})

    except WebSocketDisconnect:
        ws_alive["v"] = False
        logger.info("Client disconnected")
    except RuntimeError as e:
        if "WebSocket is not connected" not in str(e):
            raise
        ws_alive["v"] = False
        logger.info("Client disconnected before websocket receive loop started")

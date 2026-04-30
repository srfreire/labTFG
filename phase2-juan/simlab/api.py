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

import json
import logging
from contextlib import asynccontextmanager

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from simlab.orchestrator import Orchestrator

load_dotenv()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import shared

    await shared.init()
    yield
    await shared.shutdown()


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

# Colors for simulation agents (assigned round-robin by index)
SIM_AGENT_COLORS = ["#4ade80", "#fbbf24", "#a78bfa", "#f472b6", "#38bdf8", "#fb923c"]

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


@app.websocket("/ws")
async def websocket_chat(ws: WebSocket):
    """Main WebSocket endpoint — one Orchestrator per connection."""
    await ws.accept()

    client = anthropic.AsyncAnthropic()
    orch = Orchestrator(client=client)

    # Send initial agent states + color palette to the UI
    await ws.send_json(
        {
            "type": "agents",
            "agents": _build_agent_states(),
            "pipeline": [],
            "simColors": SIM_AGENT_COLORS,
        }
    )

    # Wire up internal tool call notifications
    async def _on_agent_tool(agent_name: str, tool_name: str):
        await ws.send_json(
            {"type": "agent_tool", "agent": agent_name, "tool": tool_name}
        )

    orch.on_agent_tool_call = _on_agent_tool

    # Monkey-patch orchestrator tools to emit real-time agent status via WebSocket
    original_build = orch._build_tools

    # Helper to send intermediate data cards as each agent finishes
    async def _send_intermediate_card(tool_name: str):
        """Send data cards to frontend as each pipeline step completes."""
        state = orch._state
        if tool_name == "create_environment" and state.get("spec"):
            spec = state["spec"]
            resources = ", ".join(
                f"{r['type']} ×{r['count']}" for r in spec["resources"]
            )
            await ws.send_json(
                {
                    "type": "message",
                    "from": "orchestrator",
                    "text": f"El **Architect** ha diseñado el entorno de simulación: un grid {spec['grid']['width']}×{spec['grid']['height']} con {resources}. Ahora voy a buscar los modelos disponibles y lanzar la simulación.",
                    "card": {
                        "title": "Environment Spec",
                        "data": {
                            "Grid": f"{spec['grid']['width']} × {spec['grid']['height']}",
                            "Acciones posibles": ", ".join(
                                a["name"] if isinstance(a, dict) else str(a)
                                for a in spec["actions"]
                            ),
                            "Recursos": resources,
                        },
                    },
                }
            )
        elif tool_name == "run_simulation" and state.get("replay"):
            replay = state["replay"]
            n_agents = len(replay["frames"][0]["agents"]) if replay["frames"] else 0
            await ws.send_json(
                {
                    "type": "message",
                    "from": "orchestrator",
                    "text": f"Simulación completada: **{n_agents} agentes** durante **{replay['total_steps']} pasos**. Puedes explorar el replay paso a paso. Ahora el Tracker va a observar qué pasó.",
                    "replay": replay,
                }
            )
        elif tool_name == "observe_simulation" and state.get("tracker_output"):
            try:
                tracker = json.loads(state["tracker_output"])
                if "trajectories" in tracker:
                    n_traj = len(tracker["trajectories"])
                    episodes = tracker.get("episodes", [])
                    ep_summary = ""
                    if episodes:
                        ep_lines = []
                        for ep in episodes[:5]:
                            agent_name = ep.get("agent", "")
                            desc = ep.get("description", ep.get("type", ""))
                            ep_lines.append(
                                f"- **{agent_name}**: {desc}"
                                if agent_name
                                else f"- {desc}"
                            )
                        ep_summary = "\n\nEpisodios detectados:\n" + "\n".join(ep_lines)
                    await ws.send_json(
                        {
                            "type": "message",
                            "from": "orchestrator",
                            "text": f"El **Tracker** ha registrado las trayectorias de **{n_traj} agentes**.{ep_summary}\n\nAhora el Analyst va a buscar patrones.",
                            "tracker": tracker,
                        }
                    )
            except (json.JSONDecodeError, TypeError):
                pass
        elif tool_name == "analyze_results" and state.get("analyst_output"):
            try:
                analyst = json.loads(state["analyst_output"])
                if "patterns" in analyst:
                    n_pat = len(analyst["patterns"])
                    n_comp = len(analyst.get("comparisons", []))
                    # Include any new charts from this analysis call
                    charts = state.get("_last_charts") or []
                    chart_text = (
                        f" y generado **{len(charts)} gráficas**" if charts else ""
                    )
                    msg: dict = {
                        "type": "message",
                        "from": "orchestrator",
                        "text": f"El **Analyst** ha encontrado **{n_pat} patrones**, realizado **{n_comp} comparaciones**{chart_text}.",
                        "analyst": analyst,
                    }
                    if charts:
                        msg["charts"] = charts
                    await ws.send_json(msg)
            except (json.JSONDecodeError, TypeError):
                pass
        elif tool_name == "generate_report" and state.get("pdf_paths"):
            paths = state["pdf_paths"]
            if len(paths) == 1:
                await ws.send_json(
                    {
                        "type": "message",
                        "from": "orchestrator",
                        "text": f"El **Reporter** ha generado el informe PDF: `{paths[0]}`.",
                    }
                )
            else:
                pdf_list = "\n".join(f"- `{p}`" for p in paths)
                await ws.send_json(
                    {
                        "type": "message",
                        "from": "orchestrator",
                        "text": f"El **Reporter** ha generado **{len(paths)} informes** PDF:\n{pdf_list}",
                    }
                )

    def patched_build():
        tools, registry = original_build()
        wrapped = {}
        for tool_name, fn in registry.items():
            agent_name = TOOL_AGENT_MAP.get(tool_name)
            if agent_name:

                async def _wrapper(params, _tool=tool_name, _agent=agent_name, _fn=fn):
                    await ws.send_json(
                        {"type": "agent_status", "agent": _agent, "status": "working"}
                    )
                    try:
                        result = await _fn(params)
                    except Exception:
                        await ws.send_json(
                            {"type": "agent_status", "agent": _agent, "status": "idle"}
                        )
                        raise
                    await ws.send_json(
                        {"type": "agent_status", "agent": _agent, "status": "done"}
                    )
                    await _send_intermediate_card(_tool)
                    return result

                wrapped[tool_name] = _wrapper
            else:
                # run_simulation is not in TOOL_AGENT_MAP but we still want the card
                async def _sim_wrapper(params, _tool=tool_name, _fn=fn):
                    result = await _fn(params)
                    await _send_intermediate_card(_tool)
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

            await ws.send_json({"type": "status", "status": "thinking"})

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

                await ws.send_json(
                    {"type": "agents", "agents": agents_state, "pipeline": pipeline}
                )

                # Send the orchestrator's final text response
                # Data cards were already sent in streaming via _send_intermediate_card
                if response.strip():
                    await ws.send_json(
                        {
                            "type": "message",
                            "from": "orchestrator",
                            "text": response,
                        }
                    )

            except Exception as e:
                logger.error("Orchestrator error: %s", e, exc_info=True)
                await ws.send_json({"type": "error", "text": str(e)})

    except WebSocketDisconnect:
        logger.info("Client disconnected")

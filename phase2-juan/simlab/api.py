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
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from simlab.orchestrator import Orchestrator

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(title="DecisionLab API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Path configuration
# ---------------------------------------------------------------------------

RESEARCH_DIR = Path(__file__).resolve().parent.parent.parent / "phase1-pablo" / "examples" / "sample-run"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
BUILDER_DIR = RESEARCH_DIR / "builder"


# ---------------------------------------------------------------------------
# Agent status tracking — used by the web UI sidebar
# ---------------------------------------------------------------------------

# Single source of truth for agent names, colors, and which state key indicates "done"
AGENTS = [
    {"name": "Architect", "color": "#4ade80", "state_key": "spec"},
    {"name": "Tracker",   "color": "#fbbf24", "state_key": "tracker_output"},
    {"name": "Analyst",   "color": "#a78bfa", "state_key": "analyst_output"},
    {"name": "Reporter",  "color": "#f472b6", "state_key": "pdf_path"},
]

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
            "status": "done" if orch_state and orch_state.get(a["state_key"]) else "idle",
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
    orch = Orchestrator(
        client=client,
        research_dir=RESEARCH_DIR,
        output_dir=OUTPUT_DIR,
        builder_dir=BUILDER_DIR,
    )

    # Send initial agent states to the UI
    await ws.send_json({
        "type": "agents",
        "agents": _build_agent_states(),
        "pipeline": [],
    })

    # Monkey-patch orchestrator tools to emit real-time agent status via WebSocket
    original_build = orch._build_tools

    def patched_build():
        tools, registry = original_build()
        wrapped: dict = {}
        for tool_name, fn in registry.items():
            agent_name = TOOL_AGENT_MAP.get(tool_name)
            if agent_name:
                async def _wrapper(params, _agent=agent_name, _fn=fn):
                    await ws.send_json({"type": "agent_status", "agent": _agent, "status": "working"})
                    try:
                        result = await _fn(params)
                    except Exception:
                        await ws.send_json({"type": "agent_status", "agent": _agent, "status": "idle"})
                        raise
                    await ws.send_json({"type": "agent_status", "agent": _agent, "status": "done"})
                    return result
                wrapped[tool_name] = _wrapper
            else:
                wrapped[tool_name] = fn
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
                for key, step in [("spec", "arch"), ("events", "sim"), ("tracker_output", "track"), ("analyst_output", "anal"), ("pdf_path", "repo")]:
                    if state.get(key):
                        pipeline.append({"step": step, "status": "done"})

                await ws.send_json({"type": "agents", "agents": agents_state, "pipeline": pipeline})

                # Build response with optional data cards
                response_data: dict = {
                    "type": "message",
                    "from": "orchestrator",
                    "text": response,
                }

                # Environment spec card (shown after create_environment, before simulation)
                if state.get("spec") and not state.get("events"):
                    response_data["card"] = {
                        "title": "Environment Spec",
                        "data": {
                            "Grid": f"{state['spec']['grid']['width']} × {state['spec']['grid']['height']}",
                            "Acciones": str(len(state["spec"]["actions"])),
                            "Recursos": ", ".join(f"{r['type']} ×{r['count']}" for r in state["spec"]["resources"]),
                        },
                    }

                # Tracker data card
                if state.get("tracker_output"):
                    try:
                        tracker = json.loads(state["tracker_output"])
                        if "trajectories" in tracker:
                            response_data["tracker"] = tracker
                    except (json.JSONDecodeError, TypeError):
                        logger.warning("Failed to parse tracker output as JSON")

                # Analyst data card
                if state.get("analyst_output"):
                    try:
                        analyst = json.loads(state["analyst_output"])
                        if "patterns" in analyst:
                            response_data["analyst"] = analyst
                    except (json.JSONDecodeError, TypeError):
                        logger.warning("Failed to parse analyst output as JSON")

                # Replay data for the simulation grid animation
                if state.get("replay"):
                    response_data["replay"] = state["replay"]

                # Simulation summary card
                if state.get("events") and state.get("replay"):
                    sim_summary = {
                        "title": "Simulación completada",
                        "data": {
                            "Steps": str(state["replay"]["total_steps"]),
                            "Agentes": str(len(state["replay"]["frames"][0]["agents"]) if state["replay"]["frames"] else 0),
                        },
                    }
                    if not response_data.get("card"):
                        response_data["card"] = sim_summary

                await ws.send_json(response_data)

            except Exception as e:
                logger.error("Orchestrator error: %s", e, exc_info=True)
                await ws.send_json({"type": "error", "text": str(e)})

    except WebSocketDisconnect:
        logger.info("Client disconnected")

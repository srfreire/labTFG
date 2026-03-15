"""FastAPI backend — WebSocket API for the Orchestrator."""
from __future__ import annotations

import asyncio
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

RESEARCH_DIR = Path(__file__).resolve().parent.parent.parent / "phase1-pablo" / "examples" / "sample-run"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
BUILDER_DIR = RESEARCH_DIR / "builder"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_chat(ws: WebSocket):
    await ws.accept()

    client = anthropic.AsyncAnthropic()
    orch = Orchestrator(
        client=client,
        research_dir=RESEARCH_DIR,
        output_dir=OUTPUT_DIR,
        builder_dir=BUILDER_DIR,
    )

    # Send initial agent states
    await ws.send_json({
        "type": "agents",
        "agents": [
            {"name": "Architect", "status": "idle", "color": "#4ade80"},
            {"name": "Tracker", "status": "idle", "color": "#fbbf24"},
            {"name": "Analyst", "status": "idle", "color": "#a78bfa"},
            {"name": "Reporter", "status": "idle", "color": "#f472b6"},
        ],
        "pipeline": [],
    })

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            user_text = msg.get("message", "")

            if not user_text.strip():
                continue

            # Send "thinking" state
            await ws.send_json({"type": "status", "status": "thinking"})

            # Run orchestrator
            try:
                response = await orch.chat(user_text)

                # Determine which agents ran based on state
                agents_state = []
                state = orch._state
                if state.get("spec"):
                    agents_state.append({"name": "Architect", "status": "done", "color": "#4ade80"})
                else:
                    agents_state.append({"name": "Architect", "status": "idle", "color": "#4ade80"})

                if state.get("tracker_output"):
                    agents_state.append({"name": "Tracker", "status": "done", "color": "#fbbf24"})
                elif state.get("events"):
                    agents_state.append({"name": "Tracker", "status": "idle", "color": "#fbbf24"})
                else:
                    agents_state.append({"name": "Tracker", "status": "idle", "color": "#fbbf24"})

                if state.get("analyst_output"):
                    agents_state.append({"name": "Analyst", "status": "done", "color": "#a78bfa"})
                else:
                    agents_state.append({"name": "Analyst", "status": "idle", "color": "#a78bfa"})

                if state.get("pdf_path"):
                    agents_state.append({"name": "Reporter", "status": "done", "color": "#f472b6"})
                else:
                    agents_state.append({"name": "Reporter", "status": "idle", "color": "#f472b6"})

                # Build pipeline status
                pipeline = []
                if state.get("spec"):
                    pipeline.append({"step": "arch", "status": "done"})
                if state.get("events"):
                    pipeline.append({"step": "sim", "status": "done"})
                if state.get("tracker_output"):
                    pipeline.append({"step": "track", "status": "done"})
                if state.get("analyst_output"):
                    pipeline.append({"step": "anal", "status": "done"})
                if state.get("pdf_path"):
                    pipeline.append({"step": "repo", "status": "done"})

                # Send agent states
                await ws.send_json({
                    "type": "agents",
                    "agents": agents_state,
                    "pipeline": pipeline,
                })

                # Send response with any data cards
                response_data: dict = {
                    "type": "message",
                    "from": "orchestrator",
                    "text": response,
                }

                # Attach structured data if available
                if state.get("spec") and not state.get("events"):
                    response_data["card"] = {
                        "title": "Environment Spec",
                        "data": {
                            "Grid": f"{state['spec']['grid']['width']} × {state['spec']['grid']['height']}",
                            "Acciones": str(len(state["spec"]["actions"])),
                            "Recursos": ", ".join(f"{r['type']} ×{r['count']}" for r in state["spec"]["resources"]),
                        },
                    }

                if state.get("tracker_output"):
                    try:
                        tracker = json.loads(state["tracker_output"])
                        if "trajectories" in tracker:
                            response_data["tracker"] = tracker
                    except (json.JSONDecodeError, TypeError):
                        pass

                if state.get("analyst_output"):
                    try:
                        analyst = json.loads(state["analyst_output"])
                        if "patterns" in analyst:
                            response_data["analyst"] = analyst
                    except (json.JSONDecodeError, TypeError):
                        pass

                if state.get("replay"):
                    response_data["replay"] = state["replay"]

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
                await ws.send_json({
                    "type": "error",
                    "text": str(e),
                })

    except WebSocketDisconnect:
        logger.info("Client disconnected")

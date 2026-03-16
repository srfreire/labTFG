"""Shared simulation-data tools used by Tracker and Analyst agents."""
from __future__ import annotations

import json

from simlab.environment import Event
from simlab.runtime import Registry


# --- Helpers ---

def _make_serializable(obj):
    """Recursively convert non-serializable types (tuple keys, etc.) for JSON."""
    if isinstance(obj, dict):
        return {str(k): _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(item) for item in obj]
    return obj


def _event_to_dict(event: Event) -> dict:
    """Convert an Event dataclass to a JSON-serializable dict."""
    return {
        "step": event.step,
        "agent_id": event.agent_id,
        "action": {"name": event.action.name, "params": event.action.params},
        "outcome": _make_serializable(event.outcome),
    }


def _count_actions(events: list[Event]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in events:
        counts[e.action.name] = counts.get(e.action.name, 0) + 1
    return counts


def _summarize_events(events: list[Event]) -> dict:
    """Produce a compact summary for large simulations (>500 events)."""
    agents = sorted(set(e.agent_id for e in events))
    return {
        "total_events": len(events),
        "total_steps": max(e.step for e in events) + 1 if events else 0,
        "agents": agents,
        "events_per_agent": {a: sum(1 for e in events if e.agent_id == a) for a in agents},
        "action_counts": _count_actions(events),
    }


# --- Tool schemas ---

GET_SIMULATION_EVENTS_TOOL = {
    "name": "get_simulation_events",
    "description": "Get all events from the simulation. Returns raw events if <= 500, otherwise a summary with global metrics.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

GET_AGENT_TRAJECTORY_TOOL = {
    "name": "get_agent_trajectory",
    "description": "Get all events for a specific agent, including actions, rewards, and results.",
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "The agent ID (e.g. 'agent_0')"},
        },
        "required": ["agent_id"],
    },
}

GET_AGENT_STATE_TOOL = {
    "name": "get_agent_state",
    "description": "Get the internal DecisionModel state of an agent at a specific step.",
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "The agent ID"},
            "step": {"type": "integer", "description": "The simulation step number"},
        },
        "required": ["agent_id", "step"],
    },
}


# --- Tool factory ---

def build_simulation_tools(events: list[Event]) -> tuple[list[dict], Registry]:
    """Build tool schemas and registry closed over the simulation events."""
    by_agent: dict[str, list[Event]] = {}
    for e in events:
        by_agent.setdefault(e.agent_id, []).append(e)

    async def get_simulation_events(params: dict) -> str:
        if len(events) > 500:
            return json.dumps(_summarize_events(events))
        return json.dumps([_event_to_dict(e) for e in events])

    async def get_agent_trajectory(params: dict) -> str:
        agent_id = params["agent_id"]
        agent_events = by_agent.get(agent_id, [])
        return json.dumps([_event_to_dict(e) for e in agent_events])

    async def get_agent_state(params: dict) -> str:
        agent_id = params["agent_id"]
        step = params["step"]
        agent_events = by_agent.get(agent_id, [])
        event = next((e for e in agent_events if e.step == step), None)
        if event is None:
            return json.dumps({"error": f"No event for {agent_id} at step {step}"})
        return json.dumps(_make_serializable(event.outcome.get("model_state", {})))

    schemas = [GET_SIMULATION_EVENTS_TOOL, GET_AGENT_TRAJECTORY_TOOL, GET_AGENT_STATE_TOOL]
    registry: Registry = {
        "get_simulation_events": get_simulation_events,
        "get_agent_trajectory": get_agent_trajectory,
        "get_agent_state": get_agent_state,
    }
    return schemas, registry

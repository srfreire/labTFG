"""
Shared simulation-data tools for Tracker and Analyst agents.

These tools let agents explore simulation results by querying events,
trajectories, and internal model states. The tools are created as
closures over a list of Events, so each agent gets its own read-only view.

The Analyst also gets cross-experiment tools that query the DB for
historical comparison and aggregated analysis.
"""
from __future__ import annotations

import json
from collections import Counter

from simlab.environment import Event
from simlab.loop import Registry
from shared.store import list_experiments, get_experiment


# ---------------------------------------------------------------------------
# Helpers — data conversion and summarization
# ---------------------------------------------------------------------------

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
    """Count how many times each action was used."""
    return dict(Counter(e.action.name for e in events))


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


# ---------------------------------------------------------------------------
# Tool schemas — these are sent to Claude so it knows what tools exist
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tool factory — creates closures bound to a specific simulation's events
# ---------------------------------------------------------------------------

def build_simulation_tools(events: list[Event]) -> tuple[list[dict], Registry]:
    """Build tool schemas and implementations for exploring simulation data.

    Returns (schemas, registry) where:
      - schemas: list of tool definitions to send to Claude
      - registry: dict mapping tool names to their async implementations
    """
    # Index events by agent for fast lookup
    by_agent: dict[str, list[Event]] = {}
    for e in events:
        by_agent.setdefault(e.agent_id, []).append(e)

    # --- Tool implementations (closures over `events` and `by_agent`) ---

    async def get_simulation_events(params: dict) -> str:
        """Return all events, or a summary if there are too many."""
        if len(events) > 500:
            return json.dumps(_summarize_events(events))
        return json.dumps([_event_to_dict(e) for e in events])

    async def get_agent_trajectory(params: dict) -> str:
        """Return all events for a specific agent."""
        agent_id = params["agent_id"]
        agent_events = by_agent.get(agent_id, [])
        return json.dumps([_event_to_dict(e) for e in agent_events])

    async def get_agent_state(params: dict) -> str:
        """Return the internal model state of an agent at a specific step."""
        agent_id = params["agent_id"]
        step = params["step"]
        agent_events = by_agent.get(agent_id, [])
        if step < 0 or step >= len(agent_events):
            return json.dumps({"error": f"No event for {agent_id} at step {step}"})
        return json.dumps(_make_serializable(agent_events[step].outcome.get("model_state", {})))

    schemas = [GET_SIMULATION_EVENTS_TOOL, GET_AGENT_TRAJECTORY_TOOL, GET_AGENT_STATE_TOOL]
    registry: Registry = {
        "get_simulation_events": get_simulation_events,
        "get_agent_trajectory": get_agent_trajectory,
        "get_agent_state": get_agent_state,
    }
    return schemas, registry


# ---------------------------------------------------------------------------
# Cross-experiment tools (DB) — for the Analyst
# ---------------------------------------------------------------------------

LIST_PAST_EXPERIMENTS_TOOL = {
    "name": "list_past_experiments",
    "description": "List past experiments from the database. Returns id, status, description, models used, steps, and timestamps. "
                   "Use to find experiments for cross-experiment comparison.",
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Max experiments to return (default 10)"},
        },
    },
}

GET_EXPERIMENT_ANALYSIS_TOOL = {
    "name": "get_experiment_analysis",
    "description": "Get the Tracker and Analyst results from a past experiment by ID. "
                   "Returns tracker_json and analyst_json so you can compare with the current experiment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "experiment_id": {"type": "string", "description": "UUID of the past experiment"},
        },
        "required": ["experiment_id"],
    },
}


def build_cross_experiment_tools() -> tuple[list[dict], Registry]:
    """Build tools for querying past experiments from the DB."""

    _list_keys = ("id", "status", "description", "models_used", "steps", "created_at")

    async def list_past_experiments_fn(params: dict) -> str:
        limit = params.get("limit", 10)
        exps = list_experiments(limit=limit)
        return json.dumps(
            [{k: exp.get(k) for k in _list_keys} for exp in exps],
            default=str,
        )

    async def get_experiment_analysis_fn(params: dict) -> str:
        exp_id = params["experiment_id"]
        exp = get_experiment(exp_id)
        if not exp:
            return json.dumps({"error": f"Experiment {exp_id} not found"})
        return json.dumps({
            "id": exp["id"],
            "status": exp["status"],
            "description": exp.get("description"),
            "models_used": exp.get("models_used"),
            "steps": exp.get("steps"),
            "tracker_json": exp.get("tracker_json"),
            "analyst_json": exp.get("analyst_json"),
        }, default=str)

    schemas = [LIST_PAST_EXPERIMENTS_TOOL, GET_EXPERIMENT_ANALYSIS_TOOL]
    registry: Registry = {
        "list_past_experiments": list_past_experiments_fn,
        "get_experiment_analysis": get_experiment_analysis_fn,
    }
    return schemas, registry

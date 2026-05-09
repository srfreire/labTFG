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
import uuid
from collections import Counter
from typing import TYPE_CHECKING

from sqlalchemy import select

from shared.models import Experiment as DBExperiment
from simlab.environment import Event
from simlab.loop import Registry
from simlab.utils import group_by_agent

if TYPE_CHECKING:
    from shared.database import DatabaseService
    from shared.storage import StorageService

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
    d = {
        "step": event.step,
        "agent_id": event.agent_id,
        "action": {"name": event.action.name, "params": event.action.params},
        "outcome": _make_serializable(event.outcome),
    }
    if event.perception:
        d["perception"] = _make_serializable(event.perception)
    if event.pre_state:
        d["pre_state"] = _make_serializable(event.pre_state)
    if event.available_actions:
        d["available_actions"] = event.available_actions
    return d


def _count_actions(events: list[Event]) -> dict[str, int]:
    """Count how many times each action was used."""
    return dict(Counter(e.action.name for e in events))


def _event_to_trace(e: Event) -> dict:
    """Convert an Event to a decision-trace dict (perception → action → outcome)."""
    return {
        "step": e.step,
        "agent_id": e.agent_id,
        "perception": _make_serializable(e.perception) if e.perception else None,
        "pre_state": _make_serializable(e.pre_state) if e.pre_state else None,
        "available_actions": e.available_actions or None,
        "action_chosen": {"name": e.action.name, "params": e.action.params},
        "outcome": {
            "reward": e.outcome.get("reward"),
            "action_result": e.outcome.get("action_result"),
            "post_state": _make_serializable(e.outcome.get("model_state", {})),
        },
    }


def _summarize_events(events: list[Event]) -> dict:
    """Produce a compact summary for large simulations (>500 events)."""
    agents = sorted(set(e.agent_id for e in events))
    return {
        "total_events": len(events),
        "total_steps": max(e.step for e in events) + 1 if events else 0,
        "agents": agents,
        "events_per_agent": {
            a: sum(1 for e in events if e.agent_id == a) for a in agents
        },
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
            "agent_id": {
                "type": "string",
                "description": "The agent ID (e.g. 'agent_0')",
            },
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

GET_EVENT_WINDOW_TOOL = {
    "name": "get_event_window",
    "description": (
        "Get all events in a window around a specific step. "
        "Useful for analyzing what happened before and after a critical event. "
        "Returns events for ALL agents in the [step - radius, step + radius] range, "
        "plus the critical event info if it matches a known critical event."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "center_step": {
                "type": "integer",
                "description": "The step to center the window on",
            },
            "radius": {
                "type": "integer",
                "description": "Number of steps before and after (default 10)",
            },
            "agent_id": {
                "type": "string",
                "description": "Filter to a specific agent (optional)",
            },
        },
        "required": ["center_step"],
    },
}

LIST_CRITICAL_EVENTS_TOOL = {
    "name": "list_critical_events",
    "description": (
        "List all critical events detected in the simulation (rule-based). "
        "Types: consumption (successful eat), starvation (low energy), "
        "energy_spike (big energy change), strategy_shift (action pattern change). "
        "Use this to find interesting moments to analyze with get_event_window."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

GET_DECISION_TRACE_TOOL = {
    "name": "get_decision_trace",
    "description": (
        "Get the full decision trace for one agent at one step: "
        "what the agent perceived, its internal state BEFORE deciding, "
        "the action chosen, available actions, and the outcome "
        "(reward, action result, internal state AFTER). "
        "Use this to understand WHY an agent made a specific decision."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "The agent ID"},
            "step": {"type": "integer", "description": "The simulation step number"},
        },
        "required": ["agent_id", "step"],
    },
}

COMPARE_DECISION_TRACES_TOOL = {
    "name": "compare_decision_traces",
    "description": (
        "Compare decision traces of multiple agents at the same step. "
        "Shows what each agent perceived, their internal state before deciding, "
        "what action each chose, and the outcome. "
        "Use this to understand why agents made different decisions at the same moment."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "step": {
                "type": "integer",
                "description": "The simulation step to compare",
            },
            "agent_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Agent IDs to compare (omit for all agents at that step)",
            },
        },
        "required": ["step"],
    },
}


def build_simulation_tools(
    events: list[Event],
    critical_events: list[dict] | None = None,
) -> tuple[list[dict], Registry]:
    """Build tool schemas and implementations for exploring simulation data.

    Returns (schemas, registry) where:
      - schemas: list of tool definitions to send to Claude
      - registry: dict mapping tool names to their async implementations
    """
    _critical = critical_events or []

    # Index events by agent for fast lookup
    by_agent = group_by_agent(events)

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
        """Return the internal model state of an agent at a specific simulation step."""
        agent_id = params["agent_id"]
        step = params["step"]
        agent_events = by_agent.get(agent_id, [])
        # Look up by simulation step number, not array index
        for e in agent_events:
            if e.step == step:
                return json.dumps(_make_serializable(e.outcome.get("model_state", {})))
        return json.dumps({"error": f"No event for {agent_id} at step {step}"})

    async def get_event_window(params: dict) -> str:
        """Return events in a window around a center step."""
        center = params["center_step"]
        radius = params.get("radius", 10)
        agent_filter = params.get("agent_id")
        start = max(0, center - radius)
        end = center + radius

        window_events = [
            e
            for e in events
            if start <= e.step <= end
            and (not agent_filter or e.agent_id == agent_filter)
        ]
        # Find any critical events in this window
        window_critical = [
            ce
            for ce in _critical
            if start <= ce["step"] <= end
            and (not agent_filter or ce["agent_id"] == agent_filter)
        ]
        return json.dumps(
            {
                "center_step": center,
                "range": [start, end],
                "events": [_event_to_dict(e) for e in window_events],
                "critical_events_in_window": window_critical,
            }
        )

    async def list_critical_events_fn(params: dict) -> str:
        """Return all detected critical events."""
        return json.dumps(
            {
                "total": len(_critical),
                "events": _critical,
            }
        )

    async def get_decision_trace(params: dict) -> str:
        """Return the full decision trace for one agent at one step."""
        agent_id = params["agent_id"]
        step = params["step"]
        for e in by_agent.get(agent_id, []):
            if e.step == step:
                return json.dumps(_event_to_trace(e))
        return json.dumps({"error": f"No event for {agent_id} at step {step}"})

    async def compare_decision_traces(params: dict) -> str:
        """Compare decision traces of multiple agents at the same step."""
        step = params["step"]
        agent_filter = params.get("agent_ids")
        step_events = [e for e in events if e.step == step]
        if agent_filter:
            step_events = [e for e in step_events if e.agent_id in agent_filter]
        if not step_events:
            return json.dumps({"error": f"No events at step {step}"})
        return json.dumps(
            {"step": step, "traces": [_event_to_trace(e) for e in step_events]}
        )

    schemas = [
        GET_SIMULATION_EVENTS_TOOL,
        GET_AGENT_TRAJECTORY_TOOL,
        GET_AGENT_STATE_TOOL,
        GET_EVENT_WINDOW_TOOL,
        LIST_CRITICAL_EVENTS_TOOL,
        GET_DECISION_TRACE_TOOL,
        COMPARE_DECISION_TRACES_TOOL,
    ]
    registry: Registry = {
        "get_simulation_events": get_simulation_events,
        "get_agent_trajectory": get_agent_trajectory,
        "get_agent_state": get_agent_state,
        "get_event_window": get_event_window,
        "list_critical_events": list_critical_events_fn,
        "get_decision_trace": get_decision_trace,
        "compare_decision_traces": compare_decision_traces,
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
            "limit": {
                "type": "integer",
                "description": "Max experiments to return (default 10)",
            },
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
            "experiment_id": {
                "type": "string",
                "description": "UUID of the past experiment",
            },
        },
        "required": ["experiment_id"],
    },
}


def build_cross_experiment_tools(
    *,
    db: DatabaseService,
    storage: StorageService,
) -> tuple[list[dict], Registry]:
    """Build tools for querying past experiments from Postgres + S3."""

    async def list_past_experiments_fn(params: dict) -> str:
        limit = params.get("limit", 10)
        async with db.get_session() as session:
            result = await session.execute(
                select(DBExperiment)
                .order_by(DBExperiment.created_at.desc())
                .limit(limit)
            )
            experiments = result.scalars().all()
        return json.dumps(
            [
                {
                    "id": str(e.id),
                    "status": e.status,
                    "description": e.description,
                    "models_used": e.models_used,
                    "steps": e.steps,
                    "created_at": str(e.created_at),
                }
                for e in experiments
            ],
            default=str,
        )

    async def get_experiment_analysis_fn(params: dict) -> str:
        exp_id = params["experiment_id"]
        async with db.get_session() as session:
            result = await session.execute(
                select(DBExperiment).where(DBExperiment.id == uuid.UUID(exp_id))
            )
            exp = result.scalar_one_or_none()
        if not exp:
            return json.dumps({"error": f"Experiment {exp_id} not found"})
        # Fetch tracker and analyst data from S3
        tracker_data = None
        analyst_data = None
        if exp.s3_tracker_key:
            tracker_data = await storage.get_text(exp.s3_tracker_key)
        if exp.s3_analyst_key:
            analyst_data = await storage.get_text(exp.s3_analyst_key)
        return json.dumps(
            {
                "id": str(exp.id),
                "status": exp.status,
                "description": exp.description,
                "models_used": exp.models_used,
                "steps": exp.steps,
                "tracker_json": tracker_data,
                "analyst_json": analyst_data,
            },
            default=str,
        )

    schemas = [LIST_PAST_EXPERIMENTS_TOOL, GET_EXPERIMENT_ANALYSIS_TOOL]
    registry: Registry = {
        "list_past_experiments": list_past_experiments_fn,
        "get_experiment_analysis": get_experiment_analysis_fn,
    }
    return schemas, registry

"""Tracker agent — observes simulation events and produces structured observation logs."""
from __future__ import annotations

import json

from simlab.environment import Event
from simlab.runtime import run_agent_loop, Registry
from simlab.utils import strip_markdown_fences


# --- Helpers ---

def _event_to_dict(event: Event) -> dict:
    """Convert an Event dataclass to a JSON-serializable dict."""
    return {
        "step": event.step,
        "agent_id": event.agent_id,
        "action": {"name": event.action.name, "params": event.action.params},
        "outcome": event.outcome,
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

def _build_tools(events: list[Event]) -> tuple[list[dict], Registry]:
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
        return json.dumps(event.outcome.get("model_state", {}))

    schemas = [GET_SIMULATION_EVENTS_TOOL, GET_AGENT_TRAJECTORY_TOOL, GET_AGENT_STATE_TOOL]
    registry: Registry = {
        "get_simulation_events": get_simulation_events,
        "get_agent_trajectory": get_agent_trajectory,
        "get_agent_state": get_agent_state,
    }
    return schemas, registry


# --- System prompt ---

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"

TRACKER_SYSTEM_PROMPT = """\
You are the Tracker agent for a simulation laboratory. You observe completed simulations \
and produce structured observation logs.

You have 3 tools to explore simulation data:
- get_simulation_events: overview of all events (start here)
- get_agent_trajectory: detailed events for one agent
- get_agent_state: internal model state at a specific step

## Process

1. Call get_simulation_events to understand the overall simulation
2. For each agent, call get_agent_trajectory to examine their behavior
3. Use get_agent_state to inspect internal state at interesting moments
4. Identify significant episodes (behavior changes, resource events, failures)
5. Return ONLY a valid JSON object — no markdown, no explanation

## Output schema

{
  "summary": "<1-2 sentence description of the simulation>",
  "trajectories": {
    "<agent_id>": {
      "steps_survived": int,
      "resources_consumed": int,
      "actions": {"<action_name>": count, ...}
    }
  },
  "episodes": [
    {
      "agent": "<agent_id>",
      "type": "<episode_type>",
      "steps": [start, end] or "step": int,
      "description": "<what happened and why it matters>"
    }
  ]
}

## Episode types (use these or create new descriptive ones)

- foraging_success: agent found and consumed a resource
- foraging_failure: agent searched but did not find resources
- starvation: agent state deteriorated critically
- exploration: agent moved to new areas
- exploitation: agent stayed near known resources
- state_change: significant change in internal model variables

## Rules

- Base episodes on DATA, not assumptions — cite specific steps and values
- When describing state changes, include the actual variable values from get_agent_state
- If the simulation is short (<50 steps), report all notable events
- If long (>200 steps), focus on the most significant episodes per agent
"""


# --- Tracker class ---

class Tracker:
    """Tracker agent — observes simulation events and produces structured logs."""

    def __init__(self, *, client, model: str = DEFAULT_MODEL):
        self.client = client
        self.model = model

    async def run(self, prompt: str, events: list[Event], *, max_iterations: int = 15) -> str:
        """Observe simulation events and return a structured JSON log."""
        if not events:
            return json.dumps({"summary": "No events to observe.", "trajectories": {}, "episodes": []})
        tools, registry = _build_tools(events)
        response = await run_agent_loop(
            client=self.client,
            model=self.model,
            system=TRACKER_SYSTEM_PROMPT,
            tools=tools,
            messages=[{"role": "user", "content": prompt}],
            registry=registry,
            max_iterations=max_iterations,
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        return strip_markdown_fences(text)

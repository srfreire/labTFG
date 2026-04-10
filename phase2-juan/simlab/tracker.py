"""
Tracker agent — observes simulation events and produces structured observation logs.

Flow:
  1. Receives simulation events
  2. Uses tools to explore events, trajectories, and agent states
  3. Identifies significant episodes (behavior changes, resource events)
  4. Returns a structured JSON log with summaries, trajectories, and episodes
"""
from __future__ import annotations

import json

from simlab.environment import Event
from simlab.loop import run_agent_loop
from simlab.tools import build_simulation_tools
from simlab.utils import extract_text

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

TRACKER_SYSTEM_PROMPT = """\
You are the Tracker agent for a simulation laboratory. You observe completed simulations \
and produce structured observation logs.

You have 5 tools to explore simulation data:
- get_simulation_events: overview of all events (start here)
- get_agent_trajectory: detailed events for one agent
- get_agent_state: internal model state at a specific step
- list_critical_events: list automatically detected critical moments (consumption, starvation, energy spikes, strategy shifts)
- get_event_window: get events in a window around a specific step (e.g. 10 steps before/after a critical event)

## Process

1. Call get_simulation_events to understand the overall simulation
2. Call list_critical_events to see automatically detected moments of interest
3. For each agent, call get_agent_trajectory to examine their behavior
4. Use get_event_window around critical events to understand context
5. Use get_agent_state to inspect internal state at interesting moments
6. Identify significant episodes (behavior changes, resource events, failures)
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

- ALWAYS respond in Spanish (descriptions, summaries, episode descriptions)
- Base episodes on DATA, not assumptions — cite specific steps and values
- When describing state changes, include the actual variable values from get_agent_state
- If the simulation is short (<50 steps), report all notable events
- If long (>200 steps), focus on the most significant episodes per agent
"""


# ---------------------------------------------------------------------------
# Tracker class
# ---------------------------------------------------------------------------

class Tracker:

    def __init__(self, *, client, model: str = DEFAULT_MODEL):
        self.client = client
        self.model = model

    async def run(self, prompt: str, events: list[Event], *, max_iterations: int = 15, on_tool_call=None, critical_events: list[dict] | None = None) -> str:

        if not events:
            return json.dumps({"summary": "No events to observe.", "trajectories": {}, "episodes": []})

        tools, registry = build_simulation_tools(events, critical_events=critical_events)
        response = await run_agent_loop(
            client=self.client,
            model=self.model,
            system=TRACKER_SYSTEM_PROMPT,
            tools=tools,
            messages=[{"role": "user", "content": prompt}],
            registry=registry,
            max_iterations=max_iterations,
            on_tool_call=on_tool_call,
        )
        return extract_text(response)

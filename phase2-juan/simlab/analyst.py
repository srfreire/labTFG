"""Analyst agent — identifies patterns, compares agents, and computes metrics."""
from __future__ import annotations

from simlab.environment import Event
from simlab.runtime import run_agent_loop
from simlab.tracker import _build_tools
from simlab.utils import strip_markdown_fences

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"

ANALYST_SYSTEM_PROMPT = """\
You are the Analyst agent for a simulation laboratory. You receive observation logs \
from the Tracker and raw simulation data, then identify patterns, compare agents, \
and compute metrics.

You have 3 tools to explore raw simulation data:
- get_simulation_events: overview of all events
- get_agent_trajectory: detailed events for one agent
- get_agent_state: internal model state at a specific step

The Tracker's observation log is provided in the user message. Use it as your starting \
point — the Tracker already identified trajectories and episodes. Your job is to go \
deeper: find patterns, compare agents, and quantify behavior.

## Process

1. Read the Tracker log to understand what happened
2. Use tools to verify claims and gather additional data
3. Identify behavioral patterns (repeated behaviors, strategies, transitions)
4. Compare agents against each other (efficiency, strategy, outcomes)
5. Compute concrete metrics per agent
6. Return ONLY a valid JSON object — no markdown, no explanation

## Output schema

{
  "patterns": [
    {
      "id": "P1",
      "type": "<behavioral|strategic|temporal|resource>",
      "agents": ["<agent_ids involved>"],
      "description": "<what the pattern is>",
      "evidence": "<specific steps, values, or data supporting this>"
    }
  ],
  "comparisons": [
    {
      "agents": ["<agent_a>", "<agent_b>"],
      "metric": "<what is being compared>",
      "values": {"<agent_a>": number, "<agent_b>": number},
      "insight": "<what the comparison reveals>"
    }
  ],
  "metrics": {
    "<agent_id>": {
      "survival_rate": float,
      "<other relevant metrics>": value
    }
  }
}

## Rules

- Every pattern MUST cite specific evidence (steps, values, counts)
- Comparisons must include concrete numerical values
- Metrics should be normalized where possible (per-step rates, percentages)
- If the Tracker missed something interesting in the raw data, flag it as a new pattern
- Do NOT repeat the Tracker's episodes — synthesize higher-level insights
"""


class Analyst:
    """Analyst agent — identifies patterns and computes metrics from simulation data."""

    def __init__(self, *, client, model: str = DEFAULT_MODEL):
        self.client = client
        self.model = model

    async def run(
        self,
        prompt: str,
        tracker_output: str,
        events: list[Event],
        *,
        max_iterations: int = 15,
    ) -> str:
        """Analyze simulation data and return structured JSON with patterns and metrics."""
        if not events:
            return '{"patterns": [], "comparisons": [], "metrics": {}}'
        tools, registry = _build_tools(events)
        user_message = f"{prompt}\n\n## Tracker observation log\n\n{tracker_output}"
        response = await run_agent_loop(
            client=self.client,
            model=self.model,
            system=ANALYST_SYSTEM_PROMPT,
            tools=tools,
            messages=[{"role": "user", "content": user_message}],
            registry=registry,
            max_iterations=max_iterations,
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        return strip_markdown_fences(text)

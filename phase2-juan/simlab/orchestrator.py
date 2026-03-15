"""Orchestrator agent — conversational coordinator for the simulation laboratory."""
from __future__ import annotations

import json
import random
from pathlib import Path

from simlab.architect import Architect
from simlab.tracker import Tracker
from simlab.analyst import Analyst
from simlab.reporter import Reporter
from simlab.environment import Agent, Position, Action
from simlab.runtime import run_agent_loop, Registry
from simlab.spec import spec_to_environment

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"

# --- Tool schemas ---

CREATE_ENVIRONMENT_TOOL = {
    "name": "create_environment",
    "description": "Create a simulation environment from a natural language description. Returns a JSON spec.",
    "input_schema": {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "Description of the environment to create"},
        },
        "required": ["description"],
    },
}

RUN_SIMULATION_TOOL = {
    "name": "run_simulation",
    "description": "Run a simulation with the current environment spec. Requires create_environment first.",
    "input_schema": {
        "type": "object",
        "properties": {
            "num_agents": {"type": "integer", "description": "Number of agents to place in the simulation"},
            "steps": {"type": "integer", "description": "Number of simulation steps to run"},
            "seed": {"type": "integer", "description": "Random seed for reproducibility (optional)"},
        },
        "required": ["num_agents", "steps"],
    },
}

OBSERVE_SIMULATION_TOOL = {
    "name": "observe_simulation",
    "description": "Observe the simulation results using the Tracker agent. Requires run_simulation first.",
    "input_schema": {
        "type": "object",
        "properties": {
            "focus": {"type": "string", "description": "What to focus on when observing (optional)"},
        },
    },
}

ANALYZE_RESULTS_TOOL = {
    "name": "analyze_results",
    "description": "Analyze simulation results using the Analyst agent. Requires observe_simulation first.",
    "input_schema": {
        "type": "object",
        "properties": {
            "focus": {"type": "string", "description": "What to focus on in the analysis (optional)"},
        },
    },
}

GENERATE_REPORT_TOOL = {
    "name": "generate_report",
    "description": "Generate a PDF report with all results. Requires analyze_results first.",
    "input_schema": {
        "type": "object",
        "properties": {
            "focus": {"type": "string", "description": "What to emphasize in the report (optional)"},
        },
    },
}

ALL_TOOLS = [
    CREATE_ENVIRONMENT_TOOL,
    RUN_SIMULATION_TOOL,
    OBSERVE_SIMULATION_TOOL,
    ANALYZE_RESULTS_TOOL,
    GENERATE_REPORT_TOOL,
]

# --- System prompt ---

ORCHESTRATOR_SYSTEM_PROMPT = """\
You are the Orchestrator of a virtual simulation laboratory (DecisionLab). You coordinate \
4 specialized agents to help the user create, run, observe, analyze, and report on \
simulations of decision-making paradigms.

## Your agents (call them via tools)

1. **create_environment** — generates a simulation environment spec from a description
2. **run_simulation** — runs the simulation with agents in the environment
3. **observe_simulation** — the Tracker observes what happened (trajectories, episodes)
4. **analyze_results** — the Analyst finds patterns and compares agents
5. **generate_report** — the Reporter creates a PDF with everything

## How to respond

- Respond in the same language as the user (Spanish or English)
- Be conversational, curious, and proactive — you are a research collaborator, not a command executor
- After each step, summarize what happened and SUGGEST what to explore next
- Highlight the most interesting or surprising findings

## Proactive behavior — THIS IS CRITICAL

After running a simulation, DO NOT automatically call observe_simulation. Instead:
1. Briefly describe what happened (how many events, agents, steps)
2. Suggest 2-3 interesting things to observe based on the simulation data
3. Ask the user what they want to focus on
4. ONLY THEN call observe_simulation with the user's focus

After the Tracker reports, DO NOT automatically call analyze_results. Instead:
1. Summarize the key episodes and trajectories
2. Suggest specific comparisons or patterns worth analyzing
3. Ask the user what analysis they want
4. ONLY THEN call analyze_results with the user's focus

The user guides the exploration. You propose, they decide.

EXCEPTION: If the user explicitly asks for the full pipeline ("hazlo todo", "quiero un informe completo"), \
then run all steps automatically with sensible defaults.

## Pipeline order

create_environment → run_simulation → [ask user] → observe_simulation → [ask user] → analyze_results → generate_report

- Always call create_environment before run_simulation
- Always call run_simulation before observe_simulation
- Always call observe_simulation before analyze_results
- Always call analyze_results before generate_report
- You can skip generate_report if the user only wants data
"""


# --- Dummy model for testing ---

class _DummyModel:
    """Simple foraging agent for testing without Phase 1 models."""

    def __init__(self, action_names: list[str], rng: random.Random):
        self._rng = rng
        self._hunger = 0
        self._eat = next((a for a in action_names if "eat" in a or "comer" in a), None)
        self._rest = next((a for a in action_names if "rest" in a or "descansar" in a or "esperar" in a), None)
        self._moves = [a for a in action_names if a != self._eat and a != self._rest]

    def decide(self, perception: dict) -> Action:
        self._hunger += 1
        if self._eat:
            food_key = next((k for k in perception.get("resources", {}) if "food" in k or "comida" in k), None)
            food = perception.get("resources", {}).get(food_key, []) if food_key else []
            for f in food:
                if f["x"] == perception["x"] and f["y"] == perception["y"]:
                    return Action(name=self._eat)
        if self._moves:
            return Action(name=self._rng.choice(self._moves))
        return Action(name=self._rest or self._moves[0] if self._moves else "stay")

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        if reward > 0:
            self._hunger = 0

    def get_state(self) -> dict:
        return {"hunger": self._hunger}


# --- Orchestrator class ---

class Orchestrator:
    """Conversational orchestrator that coordinates the 4 simulation agents."""

    def __init__(
        self,
        *,
        client,
        decision_models: list | None = None,
        research_dir: Path,
        output_dir: Path,
        model: str = DEFAULT_MODEL,
    ):
        self.client = client
        self.decision_models = decision_models or []
        self.research_dir = research_dir
        self.output_dir = output_dir
        self.model = model
        self._state: dict = {}
        self._messages: list[dict] = []

    async def chat(self, user_message: str) -> str:
        """Process a user message and return the orchestrator's response."""
        self._messages.append({"role": "user", "content": user_message})
        tools, registry = self._build_tools()

        response = await run_agent_loop(
            client=self.client,
            model=self.model,
            system=ORCHESTRATOR_SYSTEM_PROMPT,
            tools=tools,
            messages=self._messages,
            registry=registry,
            max_iterations=25,
            max_tokens=4096,
        )

        text = next((b.text for b in response.content if b.type == "text"), "")
        self._messages.append({"role": "assistant", "content": response.content})
        return text

    def _build_tools(self) -> tuple[list[dict], Registry]:
        state = self._state
        client = self.client

        async def create_environment(params: dict) -> str:
            arch = Architect(client=client)
            spec_json = await arch.run(params["description"])
            state["spec"] = json.loads(spec_json)
            state["events"] = None
            state["tracker_output"] = None
            state["analyst_output"] = None
            return spec_json

        async def run_simulation(params: dict) -> str:
            if not state.get("spec"):
                return json.dumps({"error": "No environment created yet. Call create_environment first."})
            env = spec_to_environment(state["spec"], seed=params.get("seed"))
            num_agents = params["num_agents"]
            steps = params["steps"]
            rng = random.Random(params.get("seed"))
            action_names = [a["name"] for a in state["spec"]["actions"]]

            for i in range(num_agents):
                if i < len(self.decision_models):
                    model = self.decision_models[i]
                else:
                    model = _DummyModel(action_names, random.Random(rng.randint(0, 2**32)))
                pos = Position(rng.randint(0, env.width - 1), rng.randint(0, env.height - 1))
                env.add_agent(Agent(id=f"agent_{i}", position=pos, decision_model=model))

            events = env.run(steps=steps)
            state["events"] = events
            state["tracker_output"] = None
            state["analyst_output"] = None

            summary = {
                "agents": num_agents,
                "steps": steps,
                "total_events": len(events),
                "agents_alive": sum(1 for a in env._agents if a.alive),
            }
            return json.dumps(summary)

        async def observe_simulation(params: dict) -> str:
            if not state.get("events"):
                return json.dumps({"error": "No simulation data. Call run_simulation first."})
            tracker = Tracker(client=client)
            focus = params.get("focus", "Observa la simulacion y reporta que paso.")
            result = await tracker.run(focus, state["events"])
            state["tracker_output"] = result
            return result

        async def analyze_results(params: dict) -> str:
            if not state.get("tracker_output"):
                return json.dumps({"error": "No observations yet. Call observe_simulation first."})
            analyst = Analyst(client=client)
            focus = params.get("focus", "Analiza patrones y compara los agentes.")
            result = await analyst.run(focus, state["tracker_output"], state["events"])
            state["analyst_output"] = result
            return result

        async def generate_report(params: dict) -> str:
            if not state.get("analyst_output"):
                return json.dumps({"error": "No analysis yet. Call analyze_results first."})
            reporter = Reporter(client=client)
            focus = params.get("focus", "Genera un informe completo de la simulacion.")
            result = await reporter.run(
                focus,
                state["tracker_output"],
                state["analyst_output"],
                research_dir=self.research_dir,
                output_dir=self.output_dir,
            )
            pdf_path = self.output_dir / "report.pdf"
            if pdf_path.exists():
                state["pdf_path"] = str(pdf_path)
            return result

        registry: Registry = {
            "create_environment": create_environment,
            "run_simulation": run_simulation,
            "observe_simulation": observe_simulation,
            "analyze_results": analyze_results,
            "generate_report": generate_report,
        }
        return ALL_TOOLS, registry

"""
Orchestrator agent — conversational coordinator for the simulation laboratory.

The Orchestrator is the main entry point. It:
  1. Talks to the user via chat
  2. Coordinates the 4 specialized agents (Architect, Tracker, Analyst, Reporter)
  3. Manages simulation state (environment spec, events, analysis results)
  4. Exposes tools that Claude calls to trigger each pipeline step

Pipeline: create_environment → run_simulation → observe_simulation → analyze_results → generate_report
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from simlab.architect import Architect
from simlab.tracker import Tracker
from simlab.analyst import Analyst
from simlab.reporter import Reporter
from simlab.environment import Agent, Position, Action
from simlab.loop import run_agent_loop, Registry
from simlab.spec import spec_to_environment

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"


# ---------------------------------------------------------------------------
# Tool schemas — what the Orchestrator can do (sent to Claude)
# ---------------------------------------------------------------------------

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
    "description": "Run a simulation with the current environment spec. Requires create_environment first. "
                   "Pass model_ids to run one or more models in the SAME environment for fair comparison.",
    "input_schema": {
        "type": "object",
        "properties": {
            "num_agents": {"type": "integer", "description": "Number of agents PER MODEL to place in the simulation (default 1)"},
            "steps": {"type": "integer", "description": "Number of simulation steps to run"},
            "seed": {"type": "integer", "description": "Random seed for reproducibility (optional)"},
            "model_ids": {"type": "array", "items": {"type": "string"}, "description": "List of model formulation IDs to run. Each gets num_agents agents. Pass a single-element array for one model."},
        },
        "required": ["steps"],
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

LIST_AVAILABLE_MODELS_TOOL = {
    "name": "list_available_models",
    "description": "List available decision models that can be used in simulations. Call this before run_simulation to let the user choose a model.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

ALL_TOOLS = [
    CREATE_ENVIRONMENT_TOOL,
    RUN_SIMULATION_TOOL,
    LIST_AVAILABLE_MODELS_TOOL,
    OBSERVE_SIMULATION_TOOL,
    ANALYZE_RESULTS_TOOL,
    GENERATE_REPORT_TOOL,
]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

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

## Model selection

Before running a simulation, call list_available_models to check what decision models are available. \
Present the options to the user and let them choose. Then pass the chosen model IDs to run_simulation via model_ids. \
If no models are available, use the built-in dummy model and tell the user.

IMPORTANT: Always use model_ids (an array) to pass model formulation IDs to run_simulation. \
For a single model: model_ids=["homeostatic-regulation_drive_reduction_rl"]. \
For comparison: model_ids=["homeostatic-regulation_drive_reduction_rl", "homeostatic-regulation_pi_negative_feedback"]. \
Each model gets its own agent(s) in the shared environment.

## Environment creation — IMPORTANT

When calling create_environment, be VERY SPECIFIC in the description. The Architect generates \
the spec from your description, so include:
- Exact grid dimensions (e.g. "8x8")
- Exact resource count and type (e.g. "5 food")
- ALL required actions: move_up, move_down, move_left, move_right, eat, stay
- The "stay" action is REQUIRED — decision models need it for energy conservation
- The "eat" action must be a ConsumeEffect with resource_type matching the resource type

Example description: "Grid 8x8, 5 food with regeneration, actions: move_up, move_down, move_left, move_right, eat (consumes food), stay"

## Pipeline order

create_environment → run_simulation → [ask user] → observe_simulation → [ask user] → analyze_results → generate_report

- Always call create_environment before run_simulation
- Always call run_simulation before observe_simulation
- Always call observe_simulation before analyze_results
- Always call analyze_results before generate_report
- You can skip generate_report if the user only wants data
"""


# ---------------------------------------------------------------------------
# Dummy model — fallback when no Phase 1 models are available
# ---------------------------------------------------------------------------

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
        # If on top of food, eat it
        if self._eat:
            food_key = next((k for k in perception.get("resources", {}) if "food" in k or "comida" in k), None)
            food = perception.get("resources", {}).get(food_key, []) if food_key else []
            for f in food:
                if f["x"] == perception["x"] and f["y"] == perception["y"]:
                    return Action(name=self._eat)
        # Otherwise, move randomly
        if self._moves:
            return Action(name=self._rng.choice(self._moves))
        return Action(name=self._rest or self._moves[0] if self._moves else "stay")

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        if reward > 0:
            self._hunger = 0

    def get_state(self) -> dict:
        return {"hunger": self._hunger}


# ---------------------------------------------------------------------------
# Orchestrator class
# ---------------------------------------------------------------------------

class Orchestrator:
    """Conversational orchestrator that coordinates the 4 simulation agents.

    Manages the full pipeline state and exposes a chat() method for interaction.
    Each tool call triggers the corresponding agent and updates internal state.
    """

    def __init__(
        self,
        *,
        client,
        decision_models: list | None = None,
        research_dir: Path,
        output_dir: Path,
        model: str = DEFAULT_MODEL,
        builder_dir: Path | None = None,
    ):
        self.client = client
        self.decision_models = decision_models or []
        self.research_dir = research_dir
        self.output_dir = output_dir
        self.model = model
        self.builder_dir = builder_dir

        # Pipeline state — tracks what has been done so far
        self._state: dict = {}
        self._messages: list[dict] = []
        self._discovered_models: dict | None = None

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
        """Build tool implementations as closures over the orchestrator's state."""
        state = self._state
        client = self.client

        # --- create_environment: calls the Architect ---
        async def create_environment(params: dict) -> str:
            arch = Architect(client=client)
            spec_json = await arch.run(params["description"])
            state["spec"] = json.loads(spec_json)
            # Reset downstream state
            state["events"] = None
            state["tracker_output"] = None
            state["analyst_output"] = None
            return spec_json

        # --- list_available_models: discovers Phase 1 models ---
        async def list_available_models(params: dict) -> str:
            if not self.builder_dir or not self.builder_dir.exists():
                return json.dumps({"models": [], "note": "No builder directory configured"})
            from simlab.model_loader import discover_models
            if self._discovered_models is None:
                self._discovered_models = discover_models(self.builder_dir)
            return json.dumps({
                "models": [
                    {"formulation_id": m.formulation_id, "class_name": m.class_name, "description": m.description}
                    for m in self._discovered_models.values()
                ]
            })

        # --- run_simulation: creates agents, runs the simulation loop ---
        async def run_simulation(params: dict) -> str:
            if not state.get("spec"):
                return json.dumps({"error": "No environment created yet. Call create_environment first."})

            env = spec_to_environment(state["spec"], seed=params.get("seed"))
            num_agents = params.get("num_agents", 1)
            steps = params["steps"]
            rng = random.Random(params.get("seed"))
            action_names = [a["name"] for a in state["spec"]["actions"]]

            # Resolve which models to use
            model_ids = params.get("model_ids") or []
            available = {}
            if model_ids and self.builder_dir:
                from simlab.model_loader import discover_models, load_model as _load
                if self._discovered_models is None:
                    self._discovered_models = discover_models(self.builder_dir)
                available = self._discovered_models

            # Create agents — one (or num_agents) per model
            models_used = []
            if model_ids:
                for mid in model_ids:
                    info = available.get(mid)
                    if not info:
                        continue
                    # Short label from formulation ID (e.g. "drive_reduction_rl")
                    parts = mid.split("_", 1)
                    label = parts[1] if len(parts) > 1 else mid[:12]
                    for i in range(num_agents):
                        model = _load(info, seed=rng.randint(0, 2**32))
                        pos = Position(rng.randint(0, env.width - 1), rng.randint(0, env.height - 1))
                        agent_id = f"{label}_{i}" if num_agents > 1 else label
                        env.add_agent(Agent(id=agent_id, position=pos, decision_model=model))
                    models_used.append(mid)
            else:
                # Fallback: injected models or dummy
                for i in range(num_agents):
                    if i < len(self.decision_models):
                        model = self.decision_models[i]
                    else:
                        model = _DummyModel(action_names, random.Random(rng.randint(0, 2**32)))
                    pos = Position(rng.randint(0, env.width - 1), rng.randint(0, env.height - 1))
                    env.add_agent(Agent(id=f"agent_{i}", position=pos, decision_model=model))
                models_used.append("dummy")

            # Run step-by-step, capturing replay frames for the web UI
            all_events = []
            replay_frames = []
            for _ in range(steps):
                if env.is_finished():
                    break
                env_state = env.get_state()
                step_events = env.step()
                all_events.extend(step_events)
                replay_frames.append({
                    "step": env_state["step"],
                    "agents": env_state["agents"],
                    "resources": [
                        {"type": r.get("type", "unknown"), "x": r["x"], "y": r["y"]}
                        for r in env_state["resources"]
                    ],
                    "actions": [
                        {"agent_id": e.agent_id, "action": e.action.name, "reward": e.outcome.get("reward", 0)}
                        for e in step_events
                    ],
                })

            # Save state for downstream agents
            state["events"] = all_events
            state["replay"] = {
                "grid_width": env.width,
                "grid_height": env.height,
                "total_steps": len(replay_frames),
                "frames": replay_frames,
            }
            state["tracker_output"] = None
            state["analyst_output"] = None

            return json.dumps({
                "agents": len(env._agents),
                "steps": steps,
                "total_events": len(all_events),
                "agents_alive": sum(1 for a in env._agents if a.alive),
                "models": models_used,
            })

        # --- observe_simulation: calls the Tracker ---
        async def observe_simulation(params: dict) -> str:
            if not state.get("events"):
                return json.dumps({"error": "No simulation data. Call run_simulation first."})
            tracker = Tracker(client=client)
            focus = params.get("focus", "Observa la simulacion y reporta que paso.")
            result = await tracker.run(focus, state["events"])
            state["tracker_output"] = result
            return result

        # --- analyze_results: calls the Analyst ---
        async def analyze_results(params: dict) -> str:
            if not state.get("tracker_output"):
                return json.dumps({"error": "No observations yet. Call observe_simulation first."})
            analyst = Analyst(client=client)
            focus = params.get("focus", "Analiza patrones y compara los agentes.")
            result = await analyst.run(focus, state["tracker_output"], state["events"])
            state["analyst_output"] = result
            return result

        # --- generate_report: calls the Reporter ---
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
            "list_available_models": list_available_models,
            "run_simulation": run_simulation,
            "observe_simulation": observe_simulation,
            "analyze_results": analyze_results,
            "generate_report": generate_report,
        }
        return ALL_TOOLS, registry

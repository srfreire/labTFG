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
from simlab.critical_events import detect_critical_events, critical_events_to_json
from simlab.environment import Agent, Position
from simlab.loop import run_agent_loop, Registry
from simlab.spec import spec_to_environment
from shared.store import (
    init_db, create_experiment, update_experiment, list_experiments,
    SIMULATED, TRACKED, ANALYZED, REPORTED,
)

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
    "description": "Generate a PDF report. Can be called MULTIPLE TIMES for different reports "
                   "(e.g. one per agent, one comparative). Each call produces a separate PDF with "
                   "a unique name. Requires analyze_results first. "
                   "Use the focus parameter to specify EXACTLY what to include or exclude.",
    "input_schema": {
        "type": "object",
        "properties": {
            "focus": {
                "type": "string",
                "description": "Detailed instructions for the Reporter: what agents to cover, "
                               "which charts/metrics to include, what sections to skip, "
                               "what tone or emphasis to use. Be specific.",
            },
            "quality": {
                "type": "string",
                "enum": ["standard", "detailed"],
                "description": "Report quality: 'standard' (fast, Haiku) or 'detailed' (deeper analysis, Sonnet)",
            },
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

LIST_EXPERIMENTS_TOOL = {
    "name": "list_experiments",
    "description": "List past experiments with their status, description, and models used. "
                   "Use when the user asks about history or wants to repeat/compare experiments.",
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Maximum number of experiments to return (default 10)"},
        },
    },
}

READ_PREDICTIONS_TOOL = {
    "name": "read_predictions",
    "description": "Read the scientific predictions for a decision-making paradigm from Phase 1 deep research. "
                   "Call this AFTER the user chooses a model and BEFORE running the simulation. "
                   "The paradigm slug is the prefix of the model formulation ID "
                   "(e.g. 'homeostatic-regulation' from 'homeostatic-regulation_drive_reduction_rl').",
    "input_schema": {
        "type": "object",
        "properties": {
            "paradigm_slug": {
                "type": "string",
                "description": "Paradigm slug matching a deep research file (e.g. 'homeostatic-regulation')",
            },
        },
        "required": ["paradigm_slug"],
    },
}

ALL_TOOLS = [
    CREATE_ENVIRONMENT_TOOL,
    RUN_SIMULATION_TOOL,
    LIST_AVAILABLE_MODELS_TOOL,
    READ_PREDICTIONS_TOOL,
    OBSERVE_SIMULATION_TOOL,
    ANALYZE_RESULTS_TOOL,
    GENERATE_REPORT_TOOL,
    LIST_EXPERIMENTS_TOOL,
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
4. **analyze_results** — the Analyst finds patterns, compares agents, AND generates charts. \
Can be called MULTIPLE TIMES with different focus to explore different aspects interactively.
5. **generate_report** — the Reporter creates a PDF with everything (including all charts)
6. **list_experiments** — shows past experiments with status and models used. Offer this when the user asks about history or wants to repeat/compare experiments.
7. **read_predictions** — reads scientific predictions from Phase 1 deep research for a paradigm

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

## Iterative analysis with charts

The Analyst now generates charts (line, bar, heatmap) alongside its text analysis. \
After the first analysis, the user can ask follow-up questions like:
- "Muéstrame la evolución de energía" → call analyze_results with focus="Genera una gráfica de la evolución de energía de cada agente"
- "¿Qué pasa en los pasos 20-50?" → call analyze_results with focus="Analiza el intervalo de pasos 20-50 con gráficas"
- "Quiero ver la Q-table" → call analyze_results with focus="Muestra los Q-values de cada agente como heatmap"
- "Compara las acciones de ambos agentes" → call analyze_results with focus="Genera una gráfica de distribución de acciones comparando los agentes"

Each call to analyze_results generates new charts that accumulate. All charts are \
included in the final report. Encourage the user to explore different aspects — \
this is the interactive analysis phase.

EXCEPTION: If the user explicitly asks for the full pipeline ("hazlo todo", "quiero un informe completo"), \
then run all steps automatically with sensible defaults.

## Report generation — human in the loop

Before generating a report, present the user with what's available and ask what to include. \
This is a collaborative step — the user decides the report's scope.

1. Summarize available data: which agents were analyzed, what charts were generated, \
what patterns/comparisons exist, what metrics are available.
2. Ask the user what they want in the report:
   - Full comprehensive report? Or focused on specific agents/aspects?
   - Which charts to include?
   - Any metrics or sections to exclude?
   - Do they want multiple reports (e.g. one per agent + one comparative)?
3. Ask about quality: estándar (fast, Haiku) or detallado (deeper, Sonnet).
4. Call generate_report with a clear focus parameter that tells the Reporter exactly what to include/exclude.

The user can request MULTIPLE reports. Each call to generate_report produces a separate PDF \
with a descriptive filename chosen by the Reporter (e.g. "analisis_drive_reduction.pdf", \
"comparativa_modelos.pdf"). Encourage this: "¿Quieres un informe individual por agente además \
del comparativo?"

If the user asked for the full pipeline automatically, default to a single standard report.

## Model selection

Before running a simulation, call list_available_models to check what decision models are available. \
Present the options to the user and let them choose. Then pass the chosen model IDs to run_simulation via model_ids. \
If no models are available, tell the user and do NOT run the simulation.

IMPORTANT: Always use model_ids (an array) to pass model formulation IDs to run_simulation. \
For a single model: model_ids=["homeostatic-regulation_drive_reduction_rl"]. \
For comparison: model_ids=["homeostatic-regulation_drive_reduction_rl", "homeostatic-regulation_pi_negative_feedback"]. \
Each model gets its own agent(s) in the shared environment.

## Predictions — THIS IS CRITICAL

After the user chooses which model(s) to use, and BEFORE running the simulation:
1. Call read_predictions with the paradigm slug for each chosen model (extract it from the formulation ID — \
the part before the first underscore after the paradigm name, e.g. "homeostatic-regulation" from \
"homeostatic-regulation_drive_reduction_rl").
2. Read the predictions returned and present them to the user in a clear, conversational way.
3. Comment on what you EXPECT to happen in this specific environment given those predictions \
(e.g. "Given homeostatic regulation theory, I expect the agent to eat more aggressively when its \
energy is low and slow down once it's satisfied").
4. Ask the user if they want to proceed with the simulation OR choose a different model.
5. ONLY THEN call run_simulation.

If the user changes their mind after seeing predictions (e.g. "let me try another model", \
"better use X instead"), that is perfectly fine — call read_predictions again for the new model \
and repeat the cycle. The user can iterate on model selection as many times as they want. \
Only the predictions for the FINAL chosen model(s) will be passed to the report.

This prediction step is essential — it sets scientific expectations that can later be validated \
against the actual simulation results. The predictions will also be included in the final report.

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

create_environment → list_available_models → [user chooses] → read_predictions → [comment & ask user] → run_simulation → [ask user] → observe_simulation → [ask user] → analyze_results → generate_report

- Always call create_environment before run_simulation
- Always call read_predictions AFTER the user chooses models and BEFORE run_simulation
- Always call run_simulation before observe_simulation
- Always call observe_simulation before analyze_results
- Always call analyze_results before generate_report
- You can skip generate_report if the user only wants data

## The conversation NEVER ends — THIS IS CRITICAL

The pipeline is NOT linear with a fixed endpoint. It is a LOOP. After generating reports \
(or at any point), the user can:
- Start a completely new simulation with different parameters or models
- Re-run the same simulation with a different seed
- Ask for more analysis on the same data ("ahora muéstrame la Q-table")
- Generate additional reports with different focus
- Compare with past experiments (list_experiments)
- Change the environment and run again
- Go back to any step: new environment, new model, new analysis, new report

After generating a report, DO NOT act like the conversation is finished. Instead, \
proactively suggest next steps:
- "¿Quieres probar con otro modelo para comparar?"
- "¿Exploramos qué pasa con más pasos de simulación?"
- "¿Te gustaría un informe enfocado en un aspecto específico?"
- "¿Empezamos un nuevo experimento con un entorno diferente?"

The session continues until the user explicitly says goodbye or closes the connection.
"""


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
        model: str = DEFAULT_MODEL,
    ):
        self.client = client
        self.model = model

        # Pipeline state — tracks what has been done so far
        self._state: dict = {}
        self._messages: list[dict] = []
        self._discovered_models: dict | None = None
        # Optional callback: (agent_name, tool_name) -> None
        self.on_agent_tool_call = None

        # Initialize experiment store (backward compat — will be removed in P3-003)
        init_db()

    @property
    def research_dir(self) -> Path:
        """Transitional — will be removed when P3-002 migrates to S3."""
        return Path(__file__).resolve().parent.parent.parent / "phase1-pablo" / "examples" / "sample-run"

    @property
    def output_dir(self) -> Path:
        """Transitional — will be removed when P3-004 migrates to S3."""
        return Path(__file__).resolve().parent.parent / "output"

    @property
    def builder_dir(self) -> Path:
        """Transitional — will be removed when P3-002 migrates to S3."""
        return self.research_dir / "builder"

    def _build_interaction_summary(self) -> str:
        """Build a structured summary of the user–orchestrator interaction.

        Extracts user messages and orchestrator tool calls from the conversation
        history to document how the experiment was conducted.
        """
        entries: list[str] = []
        for msg in self._messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "user" and isinstance(content, str):
                entries.append(f"- **Usuario**: {content}")
            elif role == "assistant":
                # content can be a list of blocks (text + tool_use)
                blocks = content if isinstance(content, list) else []
                text_parts = []
                tool_parts = []
                for block in blocks:
                    if hasattr(block, "type"):
                        if block.type == "text" and block.text.strip():
                            text_parts.append(block.text.strip())
                        elif block.type == "tool_use":
                            tool_parts.append(block.name)
                if text_parts:
                    # Truncate long orchestrator responses
                    summary = text_parts[0][:300]
                    if len(text_parts[0]) > 300:
                        summary += "…"
                    entries.append(f"- **Orquestador**: {summary}")
                if tool_parts:
                    entries.append(f"  - Herramientas invocadas: {', '.join(tool_parts)}")
        return "\n".join(entries) if entries else "No interaction history available."

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
            on_tool_call=self._make_tool_callback("Orchestrator"),
        )

        text = next((b.text for b in response.content if b.type == "text"), "")
        self._messages.append({"role": "assistant", "content": response.content})
        return text

    def _make_tool_callback(self, agent_name: str):
        """Create an on_tool_call callback scoped to an agent name."""
        cb = self.on_agent_tool_call
        if not cb:
            return None
        async def _cb(tool_name: str):
            await cb(agent_name, tool_name)
        return _cb

    def _build_tools(self) -> tuple[list[dict], Registry]:
        """Build tool implementations as closures over the orchestrator's state."""
        state = self._state
        client = self.client

        # --- create_environment: calls the Architect ---
        async def create_environment(params: dict) -> str:
            arch = Architect(client=client)
            spec_json = await arch.run(params["description"], on_tool_call=self._make_tool_callback("Architect"))
            state["spec"] = json.loads(spec_json)
            # Reset downstream state
            state["events"] = None
            state["tracker_output"] = None
            state["analyst_output"] = None
            state["predictions"] = None
            state["charts"] = []
            # Persist experiment
            exp_id = create_experiment(description=params["description"])
            state["experiment_id"] = exp_id
            update_experiment(exp_id, spec_json=spec_json)
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

        # --- read_predictions: reads deep research predictions for a paradigm ---
        async def read_predictions(params: dict) -> str:
            slug = params["paradigm_slug"]
            deep_dir = self.research_dir / "deep"
            deep_file = deep_dir / f"{slug}.md"
            if not deep_file.exists():
                return json.dumps({"error": f"No deep research file for '{slug}'. Available: {[f.stem for f in deep_dir.glob('*.md')]}"})
            content = deep_file.read_text()
            # Extract the Predictions section
            import re
            match = re.search(r'## Predictions\s*\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
            if not match:
                return json.dumps({"error": f"No '## Predictions' section found in {slug}.md"})
            predictions = match.group(1).strip()
            # Accumulate predictions per paradigm; reset downstream state
            if not state.get("predictions"):
                state["predictions"] = {}
            state["predictions"][slug] = predictions
            return json.dumps({"paradigm": slug, "predictions": predictions})

        # --- run_simulation: creates agents, runs the simulation loop ---
        async def run_simulation(params: dict) -> str:
            if not state.get("spec"):
                return json.dumps({"error": "No environment created yet. Call create_environment first."})

            env = spec_to_environment(state["spec"], seed=params.get("seed"))
            num_agents = params.get("num_agents", 1)
            steps = params["steps"]
            rng = random.Random(params.get("seed"))

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
                if not available:
                    return json.dumps({"error": "No models available. Check that builder_dir is configured correctly."})
                for mid in model_ids:
                    info = available.get(mid)
                    if not info:
                        return json.dumps({"error": f"Model '{mid}' not found. Call list_available_models to see available models."})
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
                return json.dumps({"error": "No model_ids provided. Call list_available_models first and pass the chosen model IDs."})

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

            # Detect critical events (rule-based, no LLM)
            critical = detect_critical_events(all_events)
            critical_json = critical_events_to_json(critical)

            # Save state for downstream agents
            state["events"] = all_events
            state["critical_events"] = critical_json
            state["replay"] = {
                "grid_width": env.width,
                "grid_height": env.height,
                "total_steps": len(replay_frames),
                "frames": replay_frames,
                "critical_events": critical_json,
            }
            state["tracker_output"] = None
            state["analyst_output"] = None

            # Persist simulation results
            if state.get("experiment_id"):
                events_stripped = json.dumps([
                    {
                        "step": e.step,
                        "agent_id": e.agent_id,
                        "action": {"name": e.action.name, "params": e.action.params},
                        "outcome": {k: v for k, v in e.outcome.items() if k != "model_state"},
                    }
                    for e in all_events
                ])
                update_experiment(
                    state["experiment_id"],
                    events_json=events_stripped,
                    replay_json=json.dumps(state["replay"]),
                    models_used=json.dumps(models_used),
                    steps=steps,
                    seed=params.get("seed"),
                    status=SIMULATED,
                )

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
            result = await tracker.run(
                focus, state["events"],
                on_tool_call=self._make_tool_callback("Tracker"),
                critical_events=state.get("critical_events"),
            )
            state["tracker_output"] = result
            if state.get("experiment_id"):
                update_experiment(state["experiment_id"], tracker_json=result, status=TRACKED)
            return result

        # --- analyze_results: calls the Analyst (can be called multiple times) ---
        async def analyze_results(params: dict) -> str:
            if not state.get("tracker_output"):
                return json.dumps({"error": "No observations yet. Call observe_simulation first."})
            # Initialize chart accumulator on first call
            if "charts" not in state:
                state["charts"] = []
            analyst = Analyst(client=client)
            focus = params.get("focus", "Analiza patrones y compara los agentes.")
            result = await analyst.run(
                focus,
                state["tracker_output"],
                state["events"],
                on_tool_call=self._make_tool_callback("Analyst"),
                output_dir=self.output_dir,
                charts_accumulator=state["charts"],
                critical_events=state.get("critical_events"),
            )
            state["analyst_output"] = result
            # Track new charts from this call for the WS response
            state["_last_charts"] = analyst.charts[:]
            if state.get("experiment_id"):
                update_experiment(state["experiment_id"], analyst_json=result, status=ANALYZED)
            return result

        # --- generate_report: calls the Reporter (can be called multiple times) ---
        async def generate_report(params: dict) -> str:
            if not state.get("analyst_output"):
                return json.dumps({"error": "No analysis yet. Call analyze_results first."})
            quality = params.get("quality", "standard")
            reporter_model = (
                "anthropic/claude-sonnet-4-5" if quality == "detailed"
                else "anthropic/claude-haiku-4-5"
            )
            reporter = Reporter(client=client, model=reporter_model)
            focus = params.get("focus", "Genera un informe completo de la simulacion.")
            result = await reporter.run(
                focus,
                state["tracker_output"],
                state["analyst_output"],
                research_dir=self.research_dir,
                output_dir=self.output_dir,
                on_tool_call=self._make_tool_callback("Reporter"),
                interaction_summary=self._build_interaction_summary(),
                predictions=state.get("predictions"),
                charts=state.get("charts"),
            )
            # Find any new PDFs generated by the Reporter
            if "pdf_paths" not in state:
                state["pdf_paths"] = []
            for pdf in self.output_dir.glob("*.pdf"):
                path_str = str(pdf)
                if path_str not in state["pdf_paths"]:
                    state["pdf_paths"].append(path_str)
            # Keep pdf_path pointing to the latest for backwards compat
            if state["pdf_paths"]:
                state["pdf_path"] = state["pdf_paths"][-1]
                if state.get("experiment_id"):
                    update_experiment(
                        state["experiment_id"],
                        pdf_path=json.dumps(state["pdf_paths"]),
                        status=REPORTED,
                    )
            return result

        # --- list_experiments: shows past experiments ---
        async def list_experiments_fn(params: dict) -> str:
            limit = params.get("limit", 10)
            exps = list_experiments(limit=limit)
            # Strip large JSON blobs for readability
            for exp in exps:
                for key in ("events_json", "replay_json", "tracker_json", "analyst_json"):
                    if exp.get(key):
                        exp[key] = f"[{len(exp[key])} chars]"
            return json.dumps(exps, default=str)

        registry: Registry = {
            "create_environment": create_environment,
            "list_available_models": list_available_models,
            "read_predictions": read_predictions,
            "run_simulation": run_simulation,
            "observe_simulation": observe_simulation,
            "analyze_results": analyze_results,
            "generate_report": generate_report,
            "list_experiments": list_experiments_fn,
        }
        return ALL_TOOLS, registry

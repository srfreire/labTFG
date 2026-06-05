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
import logging
import random
import re
import uuid
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import quote

from sqlalchemy import select, update

from shared.models import Experiment as DBExperiment
from shared.settings import Settings, load_settings
from simlab.analyst import Analyst
from simlab.architect import Architect
from simlab.critical_events import critical_events_to_json, detect_critical_events
from simlab.environment import Agent, Position
from simlab.loop import Registry, run_agent_loop
from simlab.model_loader import discover_models
from simlab.model_loader import load_model as _load_model
from simlab.reporter import Reporter
from simlab.spec import spec_to_environment
from simlab.tools import build_simulation_tools, event_to_trace
from simlab.tracker import Tracker

if TYPE_CHECKING:
    from shared.services import Services

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"
AUTOCOMPACT_MESSAGE_THRESHOLD = 32
AUTOCOMPACT_CHAR_THRESHOLD = 150_000
AUTOCOMPACT_KEEP_MESSAGES = 10


def _simulation_request_signature(spec: dict, params: dict) -> str:
    """Stable signature for a simulation request.

    Used to make run_simulation idempotent when the LLM repeats the exact
    same tool call in a later turn.
    """
    payload = {
        "spec": spec,
        "steps": params.get("steps"),
        "seed": params.get("seed"),
        "num_agents": params.get("num_agents", 1),
        "model_ids": params.get("model_ids") or [],
    }
    return json.dumps(payload, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# Knowledge-Backbone wiring helpers (sim-memory / P2-002)
# ---------------------------------------------------------------------------


def _to_knowledge_model_info(data: dict):
    """Translate the orchestrator-state agent model dict to simlab.knowledge.ModelInfo.

    Kept as a small local helper so `simlab.knowledge` does not depend on
    `simlab.model_loader`.
    """
    from simlab.knowledge import ModelInfo

    return ModelInfo(
        model_id=data["model_id"],
        class_name=data["class_name"],
        paradigm=data["paradigm"],
        formulation=data["formulation"],
        phase1_run_id=data.get("phase1_run_id"),
    )


async def _write_tracker_memories(writer, tracker_output: str, state: dict) -> None:
    """Build a SimulationContext from `state` and invoke the writer.

    Called from `observe_simulation` after persistence. The writer itself never
    raises (it captures internally), but the caller wraps this in try/except
    as an extra safety net.
    """
    from simlab.knowledge import SimulationContext

    spec = state.get("spec") or {}
    replay = state.get("replay") or {}
    agent_to_model_raw = state.get("agent_to_model") or {}

    width = spec.get("grid_width")
    height = spec.get("grid_height")
    environment = f"grid_{width}x{height}" if width and height else "unknown"

    frames = replay.get("frames") or []

    agent_to_model = {
        agent_id: _to_knowledge_model_info(data)
        for agent_id, data in agent_to_model_raw.items()
    }

    context = SimulationContext(
        phase2_experiment_id=str(state.get("experiment_id") or ""),
        environment=environment,
        steps=len(frames),
        seed=state.get("seed"),
        agent_to_model=agent_to_model,
    )

    result = await writer.write(tracker_output, context)
    logger.info(
        "sim-memory: wrote %d summaries, %d trajectories, %d episodes "
        "(filtered=%d, skipped=%s, %dms)",
        result.summaries_written,
        result.trajectories_written,
        result.episodes_written,
        result.episodes_filtered,
        result.skipped_reason,
        result.duration_ms,
    )


# ---------------------------------------------------------------------------
# Knowledge pre-fetch (kg-enrichment / P1-001)
# ---------------------------------------------------------------------------

# Query definitions per stage: (subsection_title, query_template, namespace, top_k)
_PREFETCH_QUERIES: dict[str, list[tuple[str, str, str, int]]] = {
    "architect": [
        (
            "Paradigm facts",
            "postulates and key properties for {paradigm}",
            "paradigm",
            3,
        ),
        (
            "Previous environments",
            "environment specifications for {paradigm}",
            "simulation",
            2,
        ),
        (
            "Formulations",
            "mathematical formulations for {paradigm}",
            "formulation",
            2,
        ),
    ],
    "analyst": [
        ("Postulates", "postulates for {paradigm}", "paradigm", 3),
        (
            "Historical simulations",
            "previous simulation results for {paradigm}",
            "simulation",
            2,
        ),
        (
            "Formulations",
            "mathematical formulations and equations for {paradigm}",
            "formulation",
            2,
        ),
    ],
    "reporter": [
        ("References", "papers and authors for {paradigm}", "meta", 5),
        ("Formulations", "mathematical formulations for {paradigm}", "formulation", 2),
    ],
}

_PREFETCH_SECTION_CHAR_LIMIT = 1_200


def _trim_prefetch_section(content: str) -> str:
    """Keep auto-injected KG context useful without bloating agent prompts."""
    normalized = content.strip()
    if len(normalized) <= _PREFETCH_SECTION_CHAR_LIMIT:
        return normalized
    return normalized[: _PREFETCH_SECTION_CHAR_LIMIT - 18].rstrip() + "\n[truncated]"


async def prefetch_knowledge(
    paradigm: str,
    stage: str,
    on_warning=None,
    *,
    enabled: bool = True,
    services: Services | None = None,
) -> str:
    """Pre-fetch KG context for an agent stage. Returns markdown or ``""``."""
    if not enabled:
        return ""
    if not paradigm:
        return ""
    if services is None:
        return ""

    queries = _PREFETCH_QUERIES.get(stage)
    if not queries:
        return ""

    import asyncio

    from simlab.recall.retrieve import _EMPTY_RESULT, retrieve_context

    async def _run_one(
        title: str, query_tpl: str, ns: str, top_k: int
    ) -> tuple[str, str]:
        """Run a single retrieve_context call, return (title, result)."""
        try:
            result = await retrieve_context(
                services=services,
                query=query_tpl.format(paradigm=paradigm),
                namespace=ns,
                top_k=top_k,
                stage=f"phase2-{stage}",
            )
            if result == _EMPTY_RESULT:
                return (title, "")
            return (title, _trim_prefetch_section(result))
        except Exception as exc:
            logger.warning("Knowledge pre-fetch failed for %s: %s", stage, exc)
            if on_warning:
                await on_warning(stage, str(exc)[:200])
            return (title, "")

    results = await asyncio.gather(
        *[_run_one(title, qt, ns, tk) for title, qt, ns, tk in queries]
    )

    sections = []
    for title, content in results:
        if content:
            sections.append(f"### {title}\n\n{content}")

    if not sections:
        return ""

    return "## Knowledge context\n\n" + "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Tool schemas — what the Orchestrator can do (sent to Claude)
# ---------------------------------------------------------------------------

CREATE_ENVIRONMENT_TOOL = {
    "name": "create_environment",
    "description": "Create a simulation environment from a natural language description. Returns a JSON spec.",
    "input_schema": {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Description of the environment to create",
            },
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
            "num_agents": {
                "type": "integer",
                "description": "Number of agents PER MODEL to place in the simulation (default 1)",
            },
            "steps": {
                "type": "integer",
                "description": "Number of simulation steps to run",
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducibility (optional)",
            },
            "model_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of model keys (paradigm/formulation) to run. Each gets num_agents agents. Pass a single-element array for one model.",
            },
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
            "focus": {
                "type": "string",
                "description": "What to focus on when observing (optional)",
            },
        },
    },
}

ANALYZE_RESULTS_TOOL = {
    "name": "analyze_results",
    "description": "Analyze simulation results using the Analyst agent. Requires observe_simulation first.",
    "input_schema": {
        "type": "object",
        "properties": {
            "focus": {
                "type": "string",
                "description": "What to focus on in the analysis (optional)",
            },
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
                "description": "Report quality: 'standard' (Haiku 4.5, fast/cheap, fine for routine reports) or 'detailed' (Sonnet 4.5, deeper analysis, use when the user asks for a thorough/final/comprehensive report)",
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

GET_TRACKER_DETAIL_TOOL = {
    "name": "get_tracker_detail",
    "description": (
        "Inspect a specific slice of the latest tracker output. "
        "observe_simulation returns a summary to keep the conversation small; "
        "call this when you need the raw episodes, per-agent trajectories, or "
        "critical events to answer a follow-up question."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "part": {
                "type": "string",
                "enum": ["episodes", "trajectories", "critical_events"],
                "description": "Which slice of the tracker output to return.",
            },
            "agent_id": {
                "type": "string",
                "description": "Filter to a specific agent (only used with part='trajectories'). Optional.",
            },
            "limit": {
                "type": "integer",
                "description": "Max number of items to return (default 20).",
            },
        },
        "required": ["part"],
    },
}

GET_ANALYST_DETAIL_TOOL = {
    "name": "get_analyst_detail",
    "description": (
        "Inspect a specific slice of the latest analyst output. "
        "analyze_results returns a summary to keep the conversation small; "
        "call this when you need the raw patterns or comparisons to answer "
        "a follow-up question."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "part": {
                "type": "string",
                "enum": ["patterns", "comparisons"],
                "description": "Which slice of the analyst output to return.",
            },
            "limit": {
                "type": "integer",
                "description": "Max number of items to return (default 20).",
            },
        },
        "required": ["part"],
    },
}

GET_SIMULATION_STEP_WINDOW_TOOL = {
    "name": "get_simulation_step_window",
    "description": (
        "Inspect events around a specific step in the latest in-memory "
        "simulation run. Use this for follow-up questions like 'qué pasó "
        "alrededor del paso 41' after run_simulation, without querying the "
        "experiment database or reprocessing the whole simulation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "center_step": {
                "type": "integer",
                "description": "The step to center the window on.",
            },
            "radius": {
                "type": "integer",
                "description": (
                    "Number of steps before and after (default 10, max 30)."
                ),
            },
            "agent_id": {
                "type": "string",
                "description": "Optional agent filter.",
            },
            "detail": {
                "type": "string",
                "enum": ["compact", "full"],
                "description": "Use compact by default; full includes perception/state blobs.",
            },
        },
        "required": ["center_step"],
    },
}

LIST_EXPERIMENTS_TOOL = {
    "name": "list_experiments",
    "description": "List past experiments with their status, description, and models used. "
    "Use when the user asks about history or wants to repeat/compare experiments.",
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of experiments to return (default 10)",
            },
        },
    },
}

READ_PREDICTIONS_TOOL = {
    "name": "read_predictions",
    "description": "Read the scientific predictions for a decision-making paradigm from Phase 1 deep research. "
    "Call this AFTER the user chooses a model and BEFORE running the simulation. "
    "The paradigm slug is the paradigm field from the model listing "
    "(e.g. 'homeostatic-regulation').",
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

QUERY_EXPERIMENTS_TOOL = {
    "name": "query_experiments",
    "description": (
        "Query the experiment database using natural language. "
        "Answers questions about past experiments, models, results, patterns, "
        "and cross-experiment comparisons."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Natural language question about experiments",
            },
        },
        "required": ["question"],
    },
}

GET_REPORT_LINKS_TOOL = {
    "name": "get_report_links",
    "description": (
        "Return download URLs for PDF reports generated in the current session. "
        "Use this when the user asks for the report link, download link, PDF, "
        "or where the generated report is."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

ALL_TOOLS = [
    CREATE_ENVIRONMENT_TOOL,
    RUN_SIMULATION_TOOL,
    LIST_AVAILABLE_MODELS_TOOL,
    READ_PREDICTIONS_TOOL,
    OBSERVE_SIMULATION_TOOL,
    GET_SIMULATION_STEP_WINDOW_TOOL,
    GET_TRACKER_DETAIL_TOOL,
    ANALYZE_RESULTS_TOOL,
    GET_ANALYST_DETAIL_TOOL,
    GENERATE_REPORT_TOOL,
    GET_REPORT_LINKS_TOOL,
    LIST_EXPERIMENTS_TOOL,
    QUERY_EXPERIMENTS_TOOL,
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
6. **get_report_links** — returns download URLs for the current session's generated PDFs. Use it when the user asks for the report link or download.
7. **list_experiments** — shows past experiments with status and models used. Offer this when the user asks about history or wants to repeat/compare experiments.
8. **read_predictions** — reads scientific predictions from Phase 1 deep research for a paradigm
9. **query_experiments** — queries the experiment database with natural language. \
Use when the user asks about past experiments, comparisons between runs, \
historical results, or anything that requires searching experiment data.

## Tool returns are slim — query for detail

`observe_simulation` and `analyze_results` return a summary (counts + a short \
text summary), NOT the full JSON output. The full data lives in the session \
state. When the user asks about specific episodes, trajectories, patterns, \
or comparisons that aren't in the summary, call:

- **get_tracker_detail(part=episodes|trajectories|critical_events)** — slices the latest tracker output
- **get_analyst_detail(part=patterns|comparisons)** — slices the latest analyst output
- **get_simulation_step_window(center_step=N, radius=R)** — reads the latest
  in-memory simulation events around a step, even before Tracker/Analyst have
  run. Use this for follow-up questions about "alrededor del paso N" in the
  current run. Prefer this over query_experiments for the active simulation.

This keeps the conversation history small and lets the user drive deep dives.

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
3. Ask about quality: estándar (Sonnet, demo-safe) or detallado (deeper Sonnet analysis).
4. Call generate_report with a clear focus parameter that tells the Reporter exactly what to include/exclude.

The user can request MULTIPLE reports. Each call to generate_report produces a separate PDF \
with a descriptive filename chosen by the Reporter (e.g. "analisis_drive_reduction.pdf", \
"comparativa_modelos.pdf"). Encourage this: "¿Quieres un informe individual por agente además \
del comparativo?"

If the user asked for the full pipeline automatically, default to a single standard report.

## Model selection

Before running a simulation, call list_available_models to check what decision models are available. \
Present the options to the user and let them choose. Then pass the chosen model keys to run_simulation via model_ids. \
If no models are available, tell the user and do NOT run the simulation.

IMPORTANT: Always use model_ids (an array) to pass model keys (paradigm/formulation) to run_simulation. \
For a single model: model_ids=["homeostatic-regulation/drive-reduction-rl"]. \
For comparison: model_ids=["homeostatic-regulation/drive-reduction-rl", "homeostatic-regulation/pi-negative-feedback"]. \
Each model gets its own agent(s) in the shared environment.

## Predictions — THIS IS CRITICAL

After the user chooses which model(s) to use, and BEFORE running the simulation:
1. Call read_predictions with the paradigm slug for each chosen model (the paradigm field from list_available_models, \
e.g. "homeostatic-regulation").
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

_KNOWLEDGE_RETRIEVAL_PROMPT_SECTION = """

## Knowledge Backbone

You have access to **retrieve_context** — a tool that queries the Knowledge Backbone \
(a graph of scientific facts, papers, postulates, paradigms, and past simulation results).

**When to use it:**
- When the user asks about scientific concepts, paradigms, authors, papers, or prior simulations
- Before answering questions that would benefit from grounded, factual knowledge
- To look up what past experiments have shown about a particular paradigm

Avoid exploratory retrieval loops. If the current conversation or tool output already \
contains enough information, answer directly. When retrieval is needed, make one targeted \
call with a small `top_k` (usually 3) and an optional namespace ("paradigm", \
"formulation", "model", "simulation", "meta").
"""


_QUERY_HISTORY_PROMPT_SECTION = """

## Past Experiments & Conversations (SQL)

You have access to **query_history** — a tool that translates a natural-language question \
into a safe read-only SQL query over the user's experiments, models, pipeline memories, \
and past chat messages, and returns a markdown table.

**When to use it:**
- When the user asks about *past* experiments, models, or runs ("¿qué experimentos he hecho con prospect theory?")
- When the user asks what *they* said earlier ("¿qué le pregunté antes sobre …?")
- When the user wants a count, listing, or filter over historical data

Call `query_history` with a single `question` string. The tool plans the SQL via Haiku, \
validates that it touches only the whitelisted tables, executes it read-only, and \
returns markdown ready to drop into the chat.
"""


QUERY_HISTORY_TOOL = {
    "name": "query_history",
    "description": (
        "Answer questions about past experiments, models, pipeline memories, and chat "
        "history by translating the question to SQL and returning a markdown table. "
        "Use for retrospective queries — not for live simulation state."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Natural-language question to translate into SQL.",
            },
        },
        "required": ["question"],
    },
}


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
        services: Services,
        model: str = DEFAULT_MODEL,
    ):
        self.client = client
        self.model = model

        # ``services`` must be constructed via ``init_services`` at the
        # entry point (api.py lifespan, CLI bootstrap) and passed in
        # explicitly. There is no module-level fallback.
        self._services = services

        # Pipeline state — tracks what has been done so far
        self._state: dict = {}
        self._messages: list[dict] = []
        self._discovered_models: dict | None = None
        # Per-instance chat session id for chat_messages persistence.
        self._session_id: uuid.UUID = uuid.uuid4()
        # tool_use_id → tool name, accumulated across turns.
        self._tool_use_names: dict[str, str] = {}
        # Optional callback: (agent_name, tool_name) -> None
        self.on_agent_tool_call = None
        # Optional callback: (payload) -> None when history is compacted.
        self.on_context_compact = None
        self._autocompact_message_threshold = AUTOCOMPACT_MESSAGE_THRESHOLD
        self._autocompact_char_threshold = AUTOCOMPACT_CHAR_THRESHOLD
        self._autocompact_keep_messages = AUTOCOMPACT_KEEP_MESSAGES

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
                    entries.append(
                        f"  - Herramientas invocadas: {', '.join(tool_parts)}"
                    )
        return "\n".join(entries) if entries else "No interaction history available."

    def _build_system_prompt(self, settings: Settings) -> str:
        """Assemble the system prompt, optionally appending knowledge sections."""
        prompt = ORCHESTRATOR_SYSTEM_PROMPT
        if settings.ENABLE_KNOWLEDGE_READ:
            prompt += _KNOWLEDGE_RETRIEVAL_PROMPT_SECTION
        if settings.ENABLE_QUERY_HISTORY:
            prompt += _QUERY_HISTORY_PROMPT_SECTION
        return prompt

    async def chat(self, user_message: str) -> str:
        """Process a user message and return the orchestrator's response."""
        turn_start = len(self._messages)
        self._messages.append({"role": "user", "content": user_message})
        settings = load_settings()
        compact_payload = self._maybe_autocompact_history()
        if compact_payload is not None:
            turn_start = len(self._messages) - 1
            if self.on_context_compact:
                await self.on_context_compact(compact_payload)
            if settings.ENABLE_CHAT_PERSISTENCE:
                await self._persist_context_summary(compact_payload["summary"])
        tools, registry = self._build_tools(settings)

        response = await run_agent_loop(
            client=self.client,
            model=self.model,
            system=self._build_system_prompt(settings),
            tools=tools,
            messages=self._messages,
            registry=registry,
            max_iterations=12,
            max_tokens=3072,
            on_tool_call=self._make_tool_callback("Orchestrator"),
        )

        text = next((b.text for b in response.content if b.type == "text"), "")
        self._messages.append({"role": "assistant", "content": response.content})

        if settings.ENABLE_CHAT_PERSISTENCE:
            await self._persist_chat_turn(turn_start)

        return text

    def _maybe_autocompact_history(self) -> dict | None:
        """Replace old chat history with a deterministic audit summary."""
        if not self._messages:
            return None
        char_count = self._history_char_count(self._messages)
        over_message_limit = len(self._messages) > self._autocompact_message_threshold
        over_char_limit = char_count > self._autocompact_char_threshold
        if not over_message_limit and not over_char_limit:
            return None

        keep_count = max(1, self._autocompact_keep_messages)
        if len(self._messages) <= keep_count + 1:
            return None

        old_messages = self._messages[:-keep_count]
        kept_messages = self._messages[-keep_count:]
        summary = self._build_context_compaction_summary(
            old_messages,
            compacted_messages=len(old_messages),
            retained_messages=len(kept_messages),
            char_count=char_count,
        )
        self._messages = [
            {
                "role": "assistant",
                "content": summary,
            },
            *kept_messages,
        ]
        return {
            "summary": summary,
            "compacted_messages": len(old_messages),
            "retained_messages": len(kept_messages),
            "approx_chars_before": char_count,
        }

    def _build_context_compaction_summary(
        self,
        messages: list[dict],
        *,
        compacted_messages: int,
        retained_messages: int,
        char_count: int,
    ) -> str:
        """Build a compact trace that is useful to the LLM and auditable by humans."""
        user_turns: list[str] = []
        assistant_turns: list[str] = []
        tool_calls: list[str] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "user" and isinstance(content, str):
                text = content.strip()
                if text:
                    user_turns.append(text[:180])
            elif role == "assistant":
                text, tools = self._summarize_assistant_content(content)
                if text:
                    assistant_turns.append(text[:180])
                tool_calls.extend(tools)

        state_lines = self._build_state_summary_lines()
        lines = [
            "<orchestrator_internal_note>",
            "Notas internas — resumen del contexto previo de esta misma conversación.",
            "Continúa respondiendo al último mensaje del usuario con normalidad.",
            "No anuncies esta nota ni ofrezcas reiniciar la conversación: no hubo fallo, solo se liberó memoria del historial.",
            "",
            f"Turnos resumidos: {compacted_messages}. Turnos recientes conservados: {retained_messages}.",
        ]
        if state_lines:
            lines.append("Estado activo del pipeline:")
            lines.extend(f"- {line}" for line in state_lines)
        if user_turns:
            lines.append("Peticiones recientes del usuario:")
            lines.extend(f"- {text}" for text in user_turns[-8:])
        if assistant_turns:
            lines.append("Tus respuestas recientes:")
            lines.extend(f"- {text}" for text in assistant_turns[-6:])
        if tool_calls:
            lines.append("Herramientas que ya invocaste:")
            lines.append("- " + ", ".join(tool_calls[-16:]))
        if self._state.get("events"):
            lines.append(
                "Recordatorio operativo: no repitas run_simulation salvo petición explícita; "
                "para inspeccionar pasos concretos usa get_simulation_step_window."
            )
        lines.append("</orchestrator_internal_note>")
        return "\n".join(lines)

    def _build_state_summary_lines(self) -> list[str]:
        lines: list[str] = []
        if self._state.get("experiment_id"):
            lines.append(f"experiment_id={self._state['experiment_id']}")
        if self._state.get("seed") is not None:
            lines.append(f"seed={self._state['seed']}")
        replay = self._state.get("replay") or {}
        if replay:
            lines.append(f"pasos_simulados={replay.get('total_steps', '?')}")
        if self._state.get("agent_to_model"):
            agents = ", ".join(sorted(self._state["agent_to_model"].keys()))
            lines.append(f"agentes={agents}")
        completed = [
            name
            for key, name in [
                ("spec", "environment"),
                ("events", "simulation"),
                ("tracker_output", "tracker"),
                ("analyst_output", "analyst"),
                ("pdf_path", "reporter"),
            ]
            if self._state.get(key)
        ]
        if completed:
            lines.append(f"pipeline_completado={', '.join(completed)}")
        return lines

    def _summarize_assistant_content(self, content) -> tuple[str, list[str]]:
        if isinstance(content, str):
            return content.strip(), []
        if not isinstance(content, list):
            return "", []
        texts: list[str] = []
        tools: list[str] = []
        for block in content:
            block_type = getattr(block, "type", None)
            if isinstance(block, dict):
                block_type = block.get("type")
            if block_type == "text":
                text = (
                    block.get("text")
                    if isinstance(block, dict)
                    else getattr(block, "text", "")
                )
                if text and str(text).strip():
                    texts.append(str(text).strip())
            elif block_type == "tool_use":
                name = (
                    block.get("name")
                    if isinstance(block, dict)
                    else getattr(block, "name", None)
                )
                if name:
                    tools.append(str(name))
        return " ".join(texts), tools

    def _history_char_count(self, messages: list[dict]) -> int:
        try:
            return len(json.dumps(messages, default=str, ensure_ascii=False))
        except (TypeError, ValueError):
            return sum(len(str(m)) for m in messages)

    async def _persist_context_summary(self, summary: str) -> None:
        try:
            from simlab.recall import persist_messages, serialize_message

            experiment_id = self._state.get("experiment_id")
            if isinstance(experiment_id, str):
                try:
                    experiment_id = uuid.UUID(experiment_id)
                except ValueError:
                    experiment_id = None
            rows = serialize_message(
                {"role": "context_summary", "content": summary},
                session_id=self._session_id,
                experiment_id=experiment_id,
                tool_use_names=self._tool_use_names,
            )
            if not rows or self._services.db is None:
                return
            async with self._services.db.get_session() as session:
                await persist_messages(session, rows)
        except Exception:
            logger.warning("context summary persistence failed", exc_info=True)

    async def _persist_chat_turn(self, turn_start: int) -> None:
        """Persist the messages appended in this turn to ``chat_messages``.

        Wraps everything in try/except so DB connection failures (which
        happen outside ``persist_messages``'s own internal try/except,
        e.g. ``get_session()`` raising on enter) never reach ``chat()``.
        """
        try:
            from simlab.recall import persist_messages, serialize_message
            from simlab.recall.chat_history import _block_field

            self._refresh_tool_use_names(turn_start, _block_field)

            experiment_id = self._state.get("experiment_id")
            if isinstance(experiment_id, str):
                try:
                    experiment_id = uuid.UUID(experiment_id)
                except ValueError:
                    experiment_id = None

            rows: list[dict] = []
            for msg in self._messages[turn_start:]:
                rows.extend(
                    serialize_message(
                        msg,
                        session_id=self._session_id,
                        experiment_id=experiment_id,
                        tool_use_names=self._tool_use_names,
                    )
                )

            if not rows or self._services.db is None:
                return
            async with self._services.db.get_session() as session:
                await persist_messages(session, rows)
        except Exception:
            logger.warning("chat persistence failed", exc_info=True)

    def _refresh_tool_use_names(self, turn_start: int, block_field) -> None:
        """Incrementally update ``_tool_use_names`` with this turn's tool_use blocks."""
        for msg in self._messages[turn_start:]:
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if block_field(block, "type") != "tool_use":
                    continue
                block_id = block_field(block, "id")
                block_name = block_field(block, "name")
                if isinstance(block_id, str) and isinstance(block_name, str):
                    self._tool_use_names[block_id] = block_name

    async def _update_experiment(self, exp_id: str, **kwargs) -> None:
        """Update an experiment row in Postgres."""
        async with self._services.db.get_session() as session:
            await session.execute(
                update(DBExperiment)
                .where(DBExperiment.id == uuid.UUID(exp_id))
                .values(**kwargs)
            )
            await session.commit()

    def _make_tool_callback(self, agent_name: str):
        """Create an on_tool_call callback scoped to an agent name."""
        cb = self.on_agent_tool_call
        if not cb:
            return None

        async def _cb(tool_name: str):
            await cb(agent_name, tool_name)

        return _cb

    def _build_tools(
        self, settings: Settings | None = None
    ) -> tuple[list[dict], Registry]:
        """Build tool implementations as closures over the orchestrator's state."""
        if settings is None:
            settings = load_settings()
        state = self._state
        client = self.client

        # Pre-build recall extras once — each agent closure captures these.
        _recall: dict[str, tuple] = {}
        if settings.ENABLE_KNOWLEDGE_READ:
            try:
                from simlab.recall import build_recall_extras

                for stage in ("architect", "analyst", "reporter"):
                    _recall[stage] = build_recall_extras(stage, self._services)
            except Exception:
                logger.warning(
                    "Failed to initialise recall extras; running without knowledge tools."
                )

        def _recall_kwargs(stage: str) -> dict:
            """Return extra_tools/extra_registry/prompt_suffix kwargs if recall is on."""
            if stage not in _recall:
                return {}
            et, er, ps = _recall[stage]
            return {"extra_tools": et, "extra_registry": er, "prompt_suffix": ps}

        # Warning callback for KG pre-fetch (kg-enrichment / P1-002)
        async def _on_kg_warning(stage: str, message: str):
            cb = self.on_agent_tool_call
            if cb:
                await cb("KnowledgePreFetch", f"⚠ {stage}: {message}")

        async def _get_knowledge_ctx(stage: str, hint: str) -> str:
            """Pre-fetch KG context for an agent stage with shared wiring."""
            return await prefetch_knowledge(
                hint,
                stage,
                on_warning=_on_kg_warning,
                enabled=settings.ENABLE_KNOWLEDGE_READ,
                services=self._services,
            )

        # --- create_environment: calls the Architect ---
        async def create_environment(params: dict) -> str:
            desc = params["description"]
            # Idempotency: the orchestrator LLM tends to re-call this in
            # subsequent turns even after the env is finalised. Skip the
            # Architect (and the costly LLM round-trip) when the same
            # description has already been processed; the dedup in
            # _send_intermediate_card handles the visual card duplication.
            if state.get("spec") and state.get("last_create_description") == desc:
                return json.dumps(
                    {
                        **state["spec"],
                        "_note": "Environment already created with this description; reusing existing spec.",
                    }
                )
            # KG pre-fetch — use description as paradigm hint (kg-enrichment / P2-001)
            knowledge_ctx = await _get_knowledge_ctx("architect", params["description"])
            arch = Architect(client=client)
            spec_json = await arch.run(
                params["description"],
                on_tool_call=self._make_tool_callback("Architect"),
                knowledge_context=knowledge_ctx,
                **_recall_kwargs("architect"),
            )
            state["last_create_description"] = desc
            state["spec"] = json.loads(spec_json)
            # Reset downstream state
            state["events"] = None
            state["tracker_output"] = None
            state["analyst_output"] = None
            state["predictions"] = None
            state["charts"] = []
            state["agent_to_model"] = {}
            state["seed"] = None
            # Persist experiment to Postgres
            exp_id = str(uuid.uuid4())
            async with self._services.db.get_session() as session:
                exp = DBExperiment(
                    id=uuid.UUID(exp_id),
                    description=params["description"],
                    status="created",
                    spec=json.loads(spec_json),
                )
                session.add(exp)
                await session.commit()
            state["experiment_id"] = exp_id
            return spec_json

        # --- list_available_models: discovers Phase 1 models from Postgres ---
        async def list_available_models(params: dict) -> str:
            if self._discovered_models is None:
                self._discovered_models = await discover_models(db=self._services.db)
            if not self._discovered_models:
                return json.dumps(
                    {"models": [], "note": "No models registered in database"}
                )
            # Store run_id from first model for read_predictions / generate_report
            for m in self._discovered_models.values():
                if m.run_id and not state.get("run_id"):
                    state["run_id"] = m.run_id
                    break
            already_shown = state.get("models_listed", False)
            state["models_listed"] = True
            payload: dict = {
                "models": [
                    {
                        "key": key,
                        "paradigm": m.paradigm,
                        "formulation": m.formulation,
                        "class_name": m.class_name,
                        "description": m.description,
                    }
                    for key, m in self._discovered_models.items()
                ]
            }
            if already_shown:
                # The catalogue was already presented to the user in an
                # earlier turn. Without this hint, the LLM tends to re-list
                # everything verbatim on each follow-up question — but the
                # user CAN explicitly ask to see them again, so the hint
                # has to leave that door open.
                payload["_already_shown"] = True
                payload["_hint"] = (
                    "These models were already presented to the user in an earlier "
                    "message. Reference the chosen model(s) by key and proceed to "
                    "read_predictions / run_simulation. Only re-list the catalogue "
                    "verbatim if the user explicitly asks for it (e.g. 'list the "
                    "models again', 'remind me what models are available')."
                )
            return json.dumps(payload)

        # --- read_predictions: reads deep research predictions from S3 ---
        async def read_predictions(params: dict) -> str:
            from shared.models import Model as DBModel

            slug = params["paradigm_slug"]

            # Find the run_id from models that match this paradigm
            run_id = state.get("run_id")
            if not run_id:
                async with self._services.db.get_session() as session:
                    result = await session.execute(
                        select(DBModel)
                        .where(DBModel.paradigm.ilike(f"%{slug}%"))
                        .limit(1)
                    )
                    model = result.scalar_one_or_none()
                    if model and model.run_id:
                        run_id = str(model.run_id)
                        state["run_id"] = run_id

            if not run_id:
                return json.dumps(
                    {
                        "error": f"No run_id found for paradigm '{slug}'. Models may not be registered yet."
                    }
                )

            key = f"research/{run_id}/deep/{slug}.md"
            try:
                content = await self._services.storage.get_text(key)
            except Exception:
                # Try listing available deep research files for this run
                available_keys = await self._services.storage.list(
                    f"research/{run_id}/deep/"
                )
                available = [
                    k.split("/")[-1].removesuffix(".md") for k in available_keys
                ]
                return json.dumps(
                    {
                        "error": f"No deep research file for '{slug}'. Available: {available}"
                    }
                )

            match = re.search(
                r"## Predictions\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
            )
            if not match:
                return json.dumps(
                    {"error": f"No '## Predictions' section found in {slug}.md"}
                )
            predictions = match.group(1).strip()
            if not state.get("predictions"):
                state["predictions"] = {}
            state["predictions"][slug] = predictions
            return json.dumps({"paradigm": slug, "predictions": predictions})

        # --- run_simulation: creates agents, runs the simulation loop ---
        async def run_simulation(params: dict) -> str:
            if not state.get("spec"):
                return json.dumps(
                    {
                        "error": "No environment created yet. Call create_environment first."
                    }
                )
            signature = _simulation_request_signature(state["spec"], params)
            if state.get("replay") and state.get("last_run_signature") == signature:
                replay = state["replay"]
                return json.dumps(
                    {
                        "_reused": True,
                        "agents": len(replay["frames"][0]["agents"])
                        if replay.get("frames")
                        else 0,
                        "steps": replay.get("total_steps", 0),
                        "total_events": len(state.get("events") or []),
                        "models": state.get("models_used", []),
                        "note": "Simulation already exists for these parameters; reusing current run.",
                    }
                )

            env = spec_to_environment(state["spec"], seed=params.get("seed"))
            num_agents = params.get("num_agents", 1)
            steps = params["steps"]
            rng = random.Random(params.get("seed"))

            # Resolve which models to use
            model_ids = params.get("model_ids") or []
            available = {}
            if model_ids:
                if self._discovered_models is None:
                    self._discovered_models = await discover_models(
                        db=self._services.db
                    )
                available = self._discovered_models

            # Create agents — one (or num_agents) per model
            models_used = []
            agent_to_model: dict[str, dict] = {}
            if model_ids:
                if not available:
                    return json.dumps({"error": "No models available in database."})
                for mid in model_ids:
                    info = available.get(mid)
                    if not info:
                        return json.dumps(
                            {
                                "error": f"Model '{mid}' not found. Call list_available_models to see available models."
                            }
                        )
                    label = info.formulation
                    for i in range(num_agents):
                        model = await _load_model(
                            info,
                            storage=self._services.storage,
                            seed=rng.randint(0, 2**32),
                        )
                        pos = Position(
                            rng.randint(0, env.width - 1),
                            rng.randint(0, env.height - 1),
                        )
                        agent_id = f"{label}_{i}" if num_agents > 1 else label
                        env.add_agent(
                            Agent(id=agent_id, position=pos, decision_model=model)
                        )
                        agent_to_model[agent_id] = {
                            "model_id": info.id,
                            "class_name": info.class_name,
                            "paradigm": info.paradigm,
                            "formulation": info.formulation,
                            "phase1_run_id": info.run_id,
                        }
                    models_used.append(mid)
            else:
                return json.dumps(
                    {
                        "error": "No model_ids provided. Call list_available_models first and pass the chosen model IDs."
                    }
                )

            # Run step-by-step, capturing replay frames for the web UI
            all_events = []
            replay_frames = []
            for _ in range(steps):
                if env.is_finished():
                    break
                env_state = env.get_state()
                step_events = env.step()
                all_events.extend(step_events)
                replay_frames.append(
                    {
                        "step": env_state["step"],
                        "agents": env_state["agents"],
                        "resources": [
                            {"type": r.get("type", "unknown"), "x": r["x"], "y": r["y"]}
                            for r in env_state["resources"]
                        ],
                        "actions": [
                            {
                                "agent_id": e.agent_id,
                                "action": e.action.name,
                                "reward": e.outcome.get("reward", 0),
                            }
                            for e in step_events
                        ],
                    }
                )

            # Detect critical events (rule-based, no LLM)
            critical = detect_critical_events(all_events)
            critical_json = critical_events_to_json(critical)

            # Build decision traces indexed by step for the frontend
            traces: dict[int, list[dict]] = {}
            for e in all_events:
                traces.setdefault(e.step, []).append(event_to_trace(e))

            # Save state for downstream agents
            state["events"] = all_events
            state["critical_events"] = critical_json
            state["replay"] = {
                "grid_width": env.width,
                "grid_height": env.height,
                "total_steps": len(replay_frames),
                "frames": replay_frames,
                "critical_events": critical_json,
                "traces": traces,
            }
            state["tracker_output"] = None
            state["analyst_output"] = None
            state["agent_to_model"] = agent_to_model
            state["seed"] = params.get("seed")
            state["last_run_signature"] = signature
            state["models_used"] = models_used
            # Store paradigm name for KG pre-fetch (kg-enrichment / P1-002)
            if agent_to_model:
                first = next(iter(agent_to_model.values()))
                state["paradigm"] = first.get("paradigm", "")

            # Persist simulation results to S3 + Postgres
            if state.get("experiment_id"):
                exp_id = state["experiment_id"]
                events_stripped = json.dumps(
                    [
                        {
                            "step": e.step,
                            "agent_id": e.agent_id,
                            "action": {
                                "name": e.action.name,
                                "params": e.action.params,
                            },
                            "outcome": {
                                k: v for k, v in e.outcome.items() if k != "model_state"
                            },
                        }
                        for e in all_events
                    ]
                )
                events_key = f"experiments/{exp_id}/events.json"
                replay_key = f"experiments/{exp_id}/replay.json"
                await self._services.storage.put_text(events_key, events_stripped)
                await self._services.storage.put_text(
                    replay_key, json.dumps(state["replay"])
                )
                await self._update_experiment(
                    exp_id,
                    s3_events_key=events_key,
                    s3_replay_key=replay_key,
                    models_used=models_used,
                    steps=steps,
                    seed=params.get("seed"),
                    status="simulated",
                )

            return json.dumps(
                {
                    "agents": len(env._agents),
                    "steps": steps,
                    "total_events": len(all_events),
                    "agents_alive": sum(1 for a in env._agents if a.alive),
                    "models": models_used,
                }
            )

        # --- observe_simulation: calls the Tracker ---
        async def observe_simulation(params: dict) -> str:
            if not state.get("events"):
                return json.dumps(
                    {"error": "No simulation data. Call run_simulation first."}
                )
            tracker = Tracker(client=client)
            focus = params.get("focus", "Observa la simulacion y reporta que paso.")
            result = await tracker.run(
                focus,
                state["events"],
                on_tool_call=self._make_tool_callback("Tracker"),
                critical_events=state.get("critical_events"),
            )
            state["tracker_output"] = result
            if state.get("experiment_id"):
                exp_id = state["experiment_id"]
                tracker_key = f"experiments/{exp_id}/tracker.json"
                await self._services.storage.put_text(tracker_key, result)
                await self._update_experiment(
                    exp_id, s3_tracker_key=tracker_key, status="tracked"
                )

            # Knowledge-Backbone write (non-fatal — never aborts observe_simulation)
            writer = getattr(self._services, "sim_memory_writer", None)
            if writer is not None:
                try:
                    await _write_tracker_memories(writer, result, state)
                except Exception:
                    logger.exception(
                        "observe_simulation: knowledge writer raised (non-fatal)"
                    )

            # Return a slim summary to keep the orchestrator's conversation
            # history small. Full tracker output stays in state for the UI
            # card and for get_tracker_detail. Previously the full JSON
            # ended up in chat history every turn, blowing the 200K window
            # after 2-3 pipeline iterations.
            try:
                data = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return result
            return json.dumps(
                {
                    "status": "ok",
                    "summary": data.get("summary", ""),
                    "n_trajectories": len(data.get("trajectories", {})),
                    "n_episodes": len(data.get("episodes", [])),
                    "n_critical_events": len(state.get("critical_events") or []),
                    "_hint": (
                        "Full tracker output is in session state. "
                        "Call get_tracker_detail(part='episodes' | "
                        "'trajectories' | 'critical_events') to inspect."
                    ),
                }
            )

        # --- analyze_results: calls the Analyst (can be called multiple times) ---
        async def analyze_results(params: dict) -> str:
            if not state.get("tracker_output"):
                return json.dumps(
                    {"error": "No observations yet. Call observe_simulation first."}
                )
            # Initialize chart accumulator on first call
            if "charts" not in state:
                state["charts"] = []
            # KG pre-fetch (kg-enrichment / P1-002)
            knowledge_ctx = await _get_knowledge_ctx(
                "analyst", state.get("paradigm", "")
            )
            analyst = Analyst(
                client=client,
                storage=self._services.storage,
                db=self._services.db,
            )
            focus = params.get("focus", "Analiza patrones y compara los agentes.")
            result = await analyst.run(
                focus,
                state["tracker_output"],
                state["events"],
                on_tool_call=self._make_tool_callback("Analyst"),
                experiment_id=state.get("experiment_id", ""),
                charts_accumulator=state["charts"],
                critical_events=state.get("critical_events"),
                knowledge_context=knowledge_ctx,
                **_recall_kwargs("analyst"),
            )
            state["analyst_output"] = result
            # Track new charts from this call for the WS response
            state["_last_charts"] = analyst.charts[:]
            if state.get("experiment_id"):
                exp_id = state["experiment_id"]
                analyst_key = f"experiments/{exp_id}/analyst.json"
                await self._services.storage.put_text(analyst_key, result)
                await self._update_experiment(
                    exp_id, s3_analyst_key=analyst_key, status="analyzed"
                )

            # Slim return to keep conversation history small (see
            # observe_simulation comment for rationale). Full output stays
            # in state for the UI card and for get_analyst_detail.
            try:
                data = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return result
            return json.dumps(
                {
                    "status": "ok",
                    "summary": data.get("summary", ""),
                    "n_patterns": len(data.get("patterns", [])),
                    "n_comparisons": len(data.get("comparisons", [])),
                    "n_charts": len(state.get("_last_charts") or []),
                    "_hint": (
                        "Full analyst output is in session state. "
                        "Call get_analyst_detail(part='patterns' | "
                        "'comparisons') to inspect."
                    ),
                }
            )

        # --- generate_report: calls the Reporter (can be called multiple times) ---
        async def generate_report(params: dict) -> str:
            if not state.get("analyst_output"):
                return json.dumps(
                    {"error": "No analysis yet. Call analyze_results first."}
                )
            quality = params.get("quality", "standard")
            # Default Reporter model is Haiku — the report is mostly mechanical
            # (LaTeX template + structured data from the Analyst). `detailed`
            # lets the user opt into Sonnet for a thorough/final write-up.
            reporter_model = (
                "anthropic/claude-sonnet-4-5"
                if quality == "detailed"
                else "anthropic/claude-haiku-4-5"
            )
            # KG pre-fetch (kg-enrichment / P1-002)
            knowledge_ctx = await _get_knowledge_ctx(
                "reporter", state.get("paradigm", "")
            )
            reporter = Reporter(
                client=client,
                storage=self._services.storage,
                db=self._services.db,
                model=reporter_model,
            )
            focus = params.get("focus", "Genera un informe completo de la simulacion.")
            exp_id = state.get("experiment_id", "")
            result = await reporter.run(
                focus,
                state["tracker_output"],
                state["analyst_output"],
                run_id=state.get("run_id", ""),
                experiment_id=exp_id,
                on_tool_call=self._make_tool_callback("Reporter"),
                interaction_summary=self._build_interaction_summary(),
                predictions=state.get("predictions"),
                charts=state.get("charts"),
                knowledge_context=knowledge_ctx,
                **_recall_kwargs("reporter"),
            )
            # Track PDF S3 keys — read from Reporter side-channel because the
            # final LLM message is free-form text, not the compile_report JSON.
            if "pdf_paths" not in state:
                state["pdf_paths"] = []
            if (
                reporter.last_pdf_key
                and reporter.last_pdf_key not in state["pdf_paths"]
            ):
                state["pdf_paths"].append(reporter.last_pdf_key)
            if reporter.last_pdf_key:
                state["pdf_path"] = state["pdf_paths"][-1]
                if state.get("experiment_id"):
                    await self._update_experiment(
                        state["experiment_id"],
                        s3_pdf_key=state["pdf_path"],
                        status="reported",
                    )
                return result
            # No PDF was produced for THIS call — every compile attempt
            # (LLM-generated tex + fallback template) failed. The Reporter's
            # free-form reply tends to claim success regardless, so we
            # override it with an explicit error: the orchestrator LLM must
            # surface the failure instead of forwarding the hopeful text.
            logger.warning(
                "generate_report: Reporter returned without producing a PDF "
                "(last_pdf_key is unset). Surfacing as error to the user."
            )
            return json.dumps(
                {
                    "error": (
                        "Report generation failed: compile_report could not "
                        "produce a PDF. Likely cause: tectonic could not "
                        "fetch its LaTeX bundle (network/DNS) or LaTeX "
                        "errors exhausted the retry budget. Tell the user "
                        "the report did NOT generate, name the likely cause "
                        "from the focus/context, and offer to retry."
                    ),
                    "reporter_text": result,
                }
            )

        # --- list_experiments: shows past experiments ---
        async def list_experiments_fn(params: dict) -> str:
            limit = params.get("limit", 10)
            async with self._services.db.get_session() as session:
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
                        "description": e.description,
                        "status": e.status,
                        "models_used": e.models_used,
                        "steps": e.steps,
                        "created_at": str(e.created_at),
                    }
                    for e in experiments
                ],
                default=str,
            )

        # --- get_tracker_detail: query slices of the latest tracker output ---
        async def get_tracker_detail(params: dict) -> str:
            raw = state.get("tracker_output")
            if not raw:
                return json.dumps(
                    {"error": "No tracker output. Call observe_simulation first."}
                )
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return json.dumps({"error": "Tracker output is not valid JSON."})
            # Stamp the response with the experiment id so the LLM can detect
            # when state has rolled to a newer sim between calls and avoid
            # presenting stale slices as if they belonged to the current run.
            exp_id = state.get("experiment_id")
            part = params.get("part")
            limit = int(params.get("limit", 20))
            if part == "episodes":
                episodes = data.get("episodes", [])
                return json.dumps(
                    {
                        "experiment_id": exp_id,
                        "episodes": episodes[:limit],
                        "total": len(episodes),
                    }
                )
            if part == "trajectories":
                trajs = data.get("trajectories", {})
                agent_id = params.get("agent_id")
                if agent_id:
                    if agent_id not in trajs:
                        return json.dumps(
                            {
                                "error": f"Agent '{agent_id}' not in trajectories.",
                                "available": list(trajs.keys()),
                                "experiment_id": exp_id,
                            }
                        )
                    return json.dumps(
                        {"experiment_id": exp_id, agent_id: trajs[agent_id]}
                    )
                return json.dumps({"experiment_id": exp_id, "trajectories": trajs})
            if part == "critical_events":
                crit = state.get("critical_events") or []
                return json.dumps(
                    {
                        "experiment_id": exp_id,
                        "critical_events": crit[:limit],
                        "total": len(crit),
                    }
                )
            return json.dumps(
                {
                    "error": (
                        f"Unknown part '{part}'. "
                        "Use: episodes | trajectories | critical_events."
                    )
                }
            )

        # --- get_simulation_step_window: live window over latest run events ---
        async def get_simulation_step_window(params: dict) -> str:
            events = state.get("events")
            if not events:
                return json.dumps(
                    {
                        "error": (
                            "No simulation events in the current session. "
                            "Call run_simulation first."
                        )
                    }
                )

            _, sim_registry = build_simulation_tools(
                events,
                critical_events=state.get("critical_events"),
            )
            raw = await sim_registry["get_event_window"](params)
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw

            return json.dumps(
                {
                    "experiment_id": state.get("experiment_id"),
                    "center_step": data.get("center_step"),
                    "step_range": data.get("range"),
                    "radius": data.get("radius"),
                    "events": data.get("events", []),
                    "critical_events": data.get("critical_events_in_window", []),
                    "_hint": (
                        "This is a bounded window over the latest in-memory "
                        "simulation, not a database history query."
                    ),
                }
            )

        # --- get_analyst_detail: query slices of the latest analyst output ---
        async def get_analyst_detail(params: dict) -> str:
            raw = state.get("analyst_output")
            if not raw:
                return json.dumps(
                    {"error": "No analyst output. Call analyze_results first."}
                )
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return json.dumps({"error": "Analyst output is not valid JSON."})
            exp_id = state.get("experiment_id")
            part = params.get("part")
            limit = int(params.get("limit", 20))
            if part == "patterns":
                patterns = data.get("patterns", [])
                return json.dumps(
                    {
                        "experiment_id": exp_id,
                        "patterns": patterns[:limit],
                        "total": len(patterns),
                    }
                )
            if part == "comparisons":
                comparisons = data.get("comparisons", [])
                return json.dumps(
                    {
                        "experiment_id": exp_id,
                        "comparisons": comparisons[:limit],
                        "total": len(comparisons),
                    }
                )
            return json.dumps(
                {"error": f"Unknown part '{part}'. Use: patterns | comparisons."}
            )

        # --- query_experiments: NL query over the experiment database ---
        async def query_experiments(params: dict) -> str:
            from simlab.nlsql import query_experiments as _query

            return await _query(
                params["question"],
                db=self._services.db,
                storage=self._services.storage,
            )

        # --- get_report_links: current-session report download URLs ---
        async def get_report_links(params: dict) -> str:
            reports = []
            for key in state.get("pdf_paths") or []:
                filename = PurePosixPath(key).name or "report.pdf"
                reports.append(
                    {
                        "key": key,
                        "filename": filename,
                        "download_url": (
                            f"/api/reports/download?key={quote(key, safe='')}"
                        ),
                    }
                )
            if not reports:
                return json.dumps(
                    {
                        "error": (
                            "No report PDF has been generated in the current session."
                        )
                    }
                )
            return json.dumps({"reports": reports})

        registry: Registry = {
            "create_environment": create_environment,
            "list_available_models": list_available_models,
            "read_predictions": read_predictions,
            "run_simulation": run_simulation,
            "observe_simulation": observe_simulation,
            "get_simulation_step_window": get_simulation_step_window,
            "get_tracker_detail": get_tracker_detail,
            "analyze_results": analyze_results,
            "get_analyst_detail": get_analyst_detail,
            "generate_report": generate_report,
            "get_report_links": get_report_links,
            "list_experiments": list_experiments_fn,
            "query_experiments": query_experiments,
        }

        # --- Knowledge Backbone retrieval (sim-recall / P1-002) ---
        tools = list(ALL_TOOLS)
        if settings.ENABLE_KNOWLEDGE_READ:
            from simlab.recall import RETRIEVE_CONTEXT_TOOL, retrieve_context

            services = self._services

            async def retrieve_context_handler(params: dict) -> str:
                query = params.get("query")
                if not query:
                    return "## Retrieved Knowledge (0 results)\n\nNo query provided."
                return await retrieve_context(
                    services=services,
                    query=query,
                    namespace=params.get("namespace"),
                    top_k=params.get("top_k", 5),
                    stage="phase2-orchestrator",
                )

            tools.append(RETRIEVE_CONTEXT_TOOL)
            registry["retrieve_context"] = retrieve_context_handler

        # --- query_history ---
        if settings.ENABLE_QUERY_HISTORY:
            from simlab.nlsql import query_history as _query_history

            services = self._services

            async def query_history_handler(params: dict) -> str:
                question = params.get("question", "")
                if not question:
                    return "> Pregunta vacía."
                if services.db is None:
                    return "> Base de datos no disponible."
                return await _query_history(question, db=services.db)

            tools.append(QUERY_HISTORY_TOOL)
            registry["query_history"] = query_history_handler

        return tools, registry

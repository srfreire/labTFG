# Reasoner Agent — Design Spec

## Purpose

Adapts selected mathematical formulations (from the Formalizer) to a concrete simulation environment (Juan's Phase 2) and produces structured JSON specs for the Builder.

Bridges math → code: takes LaTeX formulations + env_spec → produces JSON with Python-flavored pseudocode.

**Note**: DESIGN.md originally specified the Reasoner as a single sequential agent. We changed to parallel sub-agents (1 per paradigm) because: (a) paradigms are independent, (b) having all formulations of a paradigm in context helps differentiate implementations, (c) follows the proven Formalizer pattern. DESIGN.md should be updated to reflect this.

---

## Architecture

Same pattern as the Formalizer: orchestrator class + sub-agent class, 1 sub-agent per paradigm in parallel.

```
Reasoner (orchestrator, plain Python)
  ├─ ReasonerSubAgent("homeostatic")  ─┐
  ├─ ReasonerSubAgent("hedonic")       ├─ asyncio.gather
  └─ ReasonerSubAgent("prospect_theory")┘
```

### Reasoner (`reasoner.py`)

- Plain Python, no LLM
- Discovers paradigm slugs from `formulations/*.md` (if not provided)
- Dispatches one `ReasonerSubAgent` per paradigm via `asyncio.gather`
- Collects results, logs partial failures (same pattern as Formalizer: `return_exceptions=True` + `isinstance(BaseException)`)
- Returns `ReasonerReport`

```python
class Reasoner:
    def __init__(self, *, client, reports_dir: Path): ...
    async def run(self, paradigm_slugs: list[str]) -> ReasonerReport: ...
```

### ReasonerSubAgent (`reasoner_sub.py`)

- **Model**: `claude-opus-4-6`
- **Tools**: `read_file` + `write_file` (sandboxed to `reports_dir`)
- **Agentic loop**: uses `run_agent_loop` (same as FormalizerSubAgent)
- **max_iterations**: 5
- **max_tokens**: 16384

```python
class ReasonerSubAgent:
    def __init__(self, *, client, reports_dir: Path): ...
    async def run(self, paradigm_slug: str) -> str: ...
```

Same `run()` signature as `FormalizerSubAgent`: single `paradigm_slug` argument. The `env_spec.json` path is not parameterized — the sub-agent always reads it from `env_spec.json` relative to `reports_dir` (the CLI is responsible for copying/placing it there before running the Reasoner).

#### Sub-agent flow

1. `read_file("deep/{slug}.md")` — paradigm theory
2. `read_file("formulations/{slug}.md")` — all formulations for this paradigm
3. `read_file("env_spec.json")` — environment spec from Juan (always at this fixed path within reports_dir)
4. Reason: map variables ↔ environment, adapt equations, generate decision logic
5. `write_file("reasoner/{formulation_id}.json")` for each formulation

#### Deriving `formulation_id`

The system prompt instructs the sub-agent to derive `formulation_id` from the paradigm slug + a short descriptive slug of the formulation approach (e.g., `homeostatic_pi_controller`, `homeostatic_drive_reduction_mdp`). The LLM generates these based on the formulation headings in the markdown.

---

## Error Handling

### Orchestrator level
- `asyncio.gather(*tasks, return_exceptions=True)` — same as Formalizer
- If a sub-agent raises, its paradigm is logged as failed and excluded from the report
- Other paradigms proceed normally (partial success is valid)

### Sub-agent level
- If `read_file` fails (missing file): the agentic loop surfaces the error to the LLM, which can report it in its response
- If the LLM produces malformed JSON in `write_file`: no validation at the sub-agent level — the sub-agent writes whatever it produces. Validation is deferred to the Builder (the next pipeline stage), which will fail fast on bad JSON and the human can re-route to the Reasoner.

This matches the Formalizer pattern: the Formalizer does not validate the markdown quality of its output either. Each stage trusts its LLM and the next stage catches issues.

---

## System Prompt

Key elements:

1. **Role**: "You adapt mathematical formulations to a concrete simulation environment, producing structured JSON specs that a Builder agent will implement as Python code."
2. **Perception dict template** — included as a reference for the stable fields from Juan's framework. The template is illustrative; the sub-agent should cross-reference it with the actual `env_spec.json` it reads (which specifies available actions, resource types, and grid size):
   ```
   {
     "x": int, "y": int,
     "grid_width": int, "grid_height": int,
     "step": int,
     "resources": {<type>: [{"x": int, "y": int, "type": str, ...properties from env_spec}]},
     "last_action_result": {<depends on action taken>}
   }
   ```
3. **Process**: read deep report → read formulations → read env_spec → for each formulation, produce a JSON and write it via `write_file`
4. **Pseudocode style**: Python-flavored (the Reasoner bridges math→code)
5. **Differentiation**: leverage having all formulations in context to produce distinct implementations
6. **Constraints**: ground in literature, use only actions from env_spec, map all variables to perception fields
7. **`formulation_id` derivation**: paradigm slug + short descriptive slug from the formulation heading

---

## JSON Output Schema (per formulation)

Unchanged from DESIGN.md:

```json
{
  "formulation_id": "homeostatic_pi_controller",
  "paradigm": "homeostatic",
  "name": "Homeostatic PI Controller (Jacquier variant)",
  "description": "...",
  "variables": [
    {
      "symbol": "F",
      "name": "fat_reserves",
      "description": "Body fat reserves",
      "type": "float",
      "initial_value": 50.0,
      "range": [0, 100]
    }
  ],
  "parameters": [
    {
      "symbol": "cF",
      "name": "fat_conversion_rate",
      "default": 0.3,
      "source": "Jacquier et al., 2014"
    }
  ],
  "rules": [
    {
      "id": "R1",
      "description": "Fat reserves update",
      "type": "ODE",
      "pseudocode": "dF_dt = cF * intake - alphaF * F",
      "source_postulate": "P1"
    }
  ],
  "decision_logic": {
    "description": "Agent decision rule",
    "pseudocode": [
      "if hunger > threshold and food_at_position: return Action('eat')",
      "if hunger > threshold: return Action(move_toward_nearest_food)",
      "else: return Action('stay')"
    ]
  },
  "env_mapping": {
    "perception_to_variables": {
      "ate_food": "last_action_result.consumed == true",
      "position": "(perception.x, perception.y)",
      "food_sources": "perception.resources.food"
    },
    "actions_used": ["up", "down", "left", "right", "stay", "eat"],
    "reward_source": "eat action → ConsumeEffect reward"
  },
  "expected_behaviors": [
    {
      "id": "B1",
      "description": "Hunger increases without eating",
      "test_pseudocode": "run 100 steps without food → assert hunger increases"
    }
  ],
  "references": []
}
```

---

## Domain Model

Add to `domain/models.py`:

```python
@dataclass(frozen=True)
class ReasonerReport:
    specs: dict[str, str]  # paradigm_slug → sub-agent text response
```

Same pattern as `FormalizationReport(formulations: dict[str, str])`. Each value is the sub-agent's full text response. The individual JSON files are already written to disk by the sub-agent via `write_file`; the report captures the LLM's conversational output (which may include explanations beyond the JSON).

---

## CLI Subcommand

```
decisionlab reason --reports-dir <path> --env-spec <path> [--paradigms slug1 slug2]
```

- `--reports-dir`: run directory containing `deep/`, `formulations/`, and where `reasoner/` output will be written
- `--env-spec`: path to Juan's `env_spec.json`. The CLI copies this file into `reports_dir/env_spec.json` before running the Reasoner (so `read_file` can access it within the sandbox).
- `--paradigms`: optional filter; if omitted, processes all found in `formulations/*.md`

Follows existing CLI patterns (typer, rich, _setup_logging, _run_async).

---

## Disk Layout

```
reports/<run>/
├── deep/
│   ├── homeostatic.md
│   └── hedonic.md
├── formulations/
│   ├── homeostatic.md
│   └── hedonic.md
├── env_spec.json
└── reasoner/
    ├── homeostatic_pi_controller.json
    ├── homeostatic_drive_reduction_mdp.json
    ├── hedonic_td_v1.json
    └── hedonic_rw_v3.json
```

---

## Testing

Mirror existing patterns:

- `tests/agents/test_reasoner.py` — orchestrator tests (mock sub-agent, asyncio.gather, partial failures)
- `tests/agents/test_reasoner_sub.py` — sub-agent tests (mock LLM responses, tool calls, system prompt content)
- Mock helpers: `_make_tool_use_block()`, `_make_text_block()`, `_make_response()`
- `@pytest.mark.asyncio`, `tmp_path` for disk I/O
- Integration test with `@pytest.mark.integration`

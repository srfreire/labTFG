"""BuilderSubAgent — translates JSON agent specs into Python DecisionModel implementations."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from decisionlab.config import SETTINGS
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.files import (
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    create_read_file,
    create_write_file,
)
from decisionlab.tools.tests import RUN_TESTS_SCHEMA, create_run_tests

logger = logging.getLogger(__name__)

BUILDER_SUB_SYSTEM_PROMPT = """\
You translate JSON agent specs into Python DecisionModel implementations and verify \
them with tests.

## DecisionModel contract

    def decide(self, perception: dict) -> Action
    def update(self, action: Action, reward: float, new_perception: dict) -> None
    def get_state(self) -> dict

`perception` keys: x, y, grid_width, grid_height, step, resources (dict of type → \
list of resource dicts), last_action_result (dict).

## Action dataclass

Define inline in each model file — never import from external packages:

    @dataclass
    class Action:
        name: str
        params: dict = field(default_factory=dict)

## File naming

The user message provides `paradigm_slug` and `formulation_slug`. Use these for paths:

- Model: `builder/{paradigm_slug}/{formulation_slug}_model.py`
- Tests: `builder/{paradigm_slug}/test_{formulation_slug}.py`

Example: if paradigm is `"homeostatic"` and formulation is `"pi_negative_feedback"`, \
the files are `builder/homeostatic/pi_negative_feedback_model.py` and \
`builder/homeostatic/test_pi_negative_feedback.py`.

Never create a second copy of a file with a different name. Write each file once.

## Validation

Before generating code for a spec, critically analyze it for implementability:

1. **Decision logic is implementable**: each pseudocode step must be concrete and \
unambiguous — no vague instructions like "use judgment" or "consider context". Every step \
must translate directly to Python code.
2. **Env mapping variables exist in perception**: every key in `perception_to_variables` must \
map to a field that exists in the perception template (`x`, `y`, `grid_width`, `grid_height`, \
`step`, `resources`, `last_action_result`).
3. **Expected behaviors are testable**: each `expected_behaviors[]` entry must have a \
`test_pseudocode` that can be translated into a deterministic unit test with clear \
setup, action, and assertion.

If ALL checks pass → proceed to generate code normally.
If ANY check fails → write a **validation report** instead of model/test files:

```json
{
  "formulation_id": "...",
  "paradigm": "...",
  "status": "invalid",
  "problems": [
    {"type": "ambiguous_logic", "detail": "Step 3 of decision_logic says 'choose wisely' — not translatable to code"},
    {"type": "missing_perception_key", "detail": "perception_to_variables maps 'temperature' but perception has no such key"},
    {"type": "untestable_behavior", "detail": "Behavior B2 has no test_pseudocode or its pseudocode is too vague to automate"},
    {"type": "other", "detail": "Free-text description of the problem"}
  ]
}
```

Save the validation report at `builder/{paradigm_slug}/{formulation_slug}_validation.json` using `write_file`.
Do NOT write model or test files for invalid specs.

Be strict but fair: flag genuine implementability issues, not stylistic preferences.

## Process

For EACH JSON spec:

1. `read_file` the spec.
2. **Validate** the spec (see Validation above).
3. If invalid → `write_file` the validation report (`builder/{paradigm_slug}/{formulation_slug}_validation.json`) \
and move to the next spec.
4. `write_file` the model (`builder/{paradigm_slug}/{formulation_slug}_model.py`).
5. `write_file` the tests (`builder/{paradigm_slug}/test_{formulation_slug}.py`).
6. `run_tests` on the test file.
7. If tests fail → fix via `write_file` + `run_tests` (max 3 attempts). Then next spec.

### CRITICAL: batch tool calls

You MUST call multiple tools in the same response whenever possible:
- Read ALL spec files in a single response (multiple `read_file` calls).
- Write model + tests for the same spec in a single response (two `write_file` calls).
- Run ALL test files in a single response (multiple `run_tests` calls).

Every unnecessary round-trip wastes time and tokens. Minimize iterations.

## Model structure

- `__init__`: variables from `variables[]` + parameters from `parameters[]`
- `decide(perception)`: read-only — select an action based on CURRENT state. Never modify \
state here.
- `update(action, reward, new_perception)`: apply ALL `rules[]` and ALL state updates here. \
This is the ONLY method that modifies internal state.
- `get_state()`: return dict of all variable values, including `q_values` (see below)

### Action scores (`q_values`)

`get_state()` MUST include a `q_values` key: a flat `dict[str, float]` mapping each \
action name to the model's current evaluation score for that action.

The simulation infrastructure uses `q_values` to visualize decision alternatives, \
detect confidence drops, and chart action score evolution over time.

- For Q-learning / RL models: Q-values for the current discretized state.
- For utility / control-based models: computed utility for each candidate action.
- Compute and cache scores in `update()` using `new_perception`. Initialize defaults \
in `__init__` (e.g. all zeros).
- Keys are action name strings (e.g. `"eat"`, `"stay"`, `"move_up"`). Values are floats.

### CRITICAL: decide vs update boundary

The simulation calls these methods in this order:

    pre_state = model.get_state()                     # snapshot BEFORE decide — includes q_values
    perception = env.build_perception(agent)          # no last_action_result
    action = model.decide(perception)                 # READ-ONLY — pick action from current state
    reward, result = env.apply(action)                # env executes the action
    new_perception = env.build_perception(agent)      # includes last_action_result
    model.update(action, reward, new_perception)      # WRITE — update all state + q_values here

`decide()` receives perception WITHOUT `last_action_result` (it is `{}`). \
Only `update()` receives the result of the action via `new_perception["last_action_result"]`.

Therefore:
- ALL state mutation (energy, drive, variables, learning) goes in `update()`.
- `decide()` ONLY reads `self.*` variables and perception to choose an action.
- If `decision_logic.pseudocode` in the spec mixes state updates with action selection, \
split them: state updates → `update()`, action selection → `decide()`.

Putting state updates in `decide()` WILL break the simulation. No exceptions.

## Test structure

- `from {formulation_slug}_model import ClassName, Action` (PYTHONPATH is pre-configured)
- One test per `expected_behaviors[]` entry, guided by `test_pseudocode`
- Pure unit tests, no external dependencies beyond stdlib/math
- Seed random for determinism when model uses randomness

## Constraints

- Files must be self-contained (only stdlib/math/random imports).
- Use exact variable and parameter names from the spec.
- Implement ALL rules — never skip any.
"""

_KNOWLEDGE_PROMPT_SECTION = """

## Knowledge Backbone

You have access to a knowledge backbone from past pipeline runs. Before generating \
code, call `retrieve_knowledge` to find working code patterns, test strategies, and \
common pitfalls from past model builds. Apply proven implementation patterns when the \
mathematical structure is similar.
"""



class BuilderSubAgent:
    def __init__(
        self,
        *,
        client,
        models_prefix: str,
        run_id: str | None = None,
        project_root: Path,
        knowledge_tool_schema: dict[str, Any] | None = None,
        knowledge_tool_handler: Callable[[dict], Awaitable[str]] | None = None,
    ):
        self.client = client
        self.tools: list[dict[str, Any]] = [
            READ_FILE_SCHEMA,
            WRITE_FILE_SCHEMA,
            RUN_TESTS_SCHEMA,
        ]
        self.registry: dict[str, Callable[[dict], Awaitable[str]]] = {
            "read_file": create_read_file(models_prefix),
            "write_file": create_write_file(models_prefix, run_id=run_id),
            "run_tests": create_run_tests(models_prefix, project_root),
        }

        self._has_knowledge = False
        if knowledge_tool_schema is not None and knowledge_tool_handler is not None:
            self.tools.append(knowledge_tool_schema)
            self.registry["retrieve_knowledge"] = knowledge_tool_handler
            self._has_knowledge = True

    async def run(self, spec_id: str, spec_path: str) -> str:
        logger.info(
            "BuilderSubAgent starting — spec: %s (%s)",
            spec_id,
            spec_path,
        )
        messages = [
            {
                "role": "user",
                "content": (
                    f"Implement a Python DecisionModel class for formulation: {spec_id}\n"
                    f"Read the JSON spec at: {spec_path}\n"
                    "Read the spec, implement the model, write tests, run them, "
                    "and fix any failures."
                ),
            }
        ]

        system = BUILDER_SUB_SYSTEM_PROMPT
        if self._has_knowledge:
            system += _KNOWLEDGE_PROMPT_SECTION

        response = await run_agent_loop(
            client=self.client,
            model=SETTINGS.builder.model,
            system=system,
            tools=self.tools,
            messages=messages,
            registry=self.registry,
            max_iterations=SETTINGS.builder.max_iterations,
            max_tokens=SETTINGS.builder.max_tokens,
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        content = "\n".join(text_blocks)

        logger.info(
            "BuilderSubAgent finished for: %s (%d chars)",
            spec_id,
            len(content),
        )
        return content

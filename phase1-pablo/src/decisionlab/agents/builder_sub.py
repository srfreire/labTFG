"""BuilderSubAgent — translates JSON agent specs into Python DecisionModel implementations."""

from __future__ import annotations

import logging
from pathlib import Path

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

Use the `formulation_id` field from the JSON spec EXACTLY as-is for file names. \
Do NOT rename, normalize, or transform it in any way.

- Model: `builder/{formulation_id}_model.py`
- Tests: `builder/test_{formulation_id}.py`

Example: if `formulation_id` is `"homeostatic-regulation_pi_negative_feedback"`, \
the files are `builder/homeostatic-regulation_pi_negative_feedback_model.py` and \
`builder/test_homeostatic-regulation_pi_negative_feedback.py`.

Never create a second copy of a file with a different name. Write each file once.

## Process

For EACH JSON spec:

1. `read_file` the spec.
2. `write_file` the model (`builder/{formulation_id}_model.py`).
3. `write_file` the tests (`builder/test_{formulation_id}.py`).
4. `run_tests` on the test file.
5. If tests fail → fix via `write_file` + `run_tests` (max 3 attempts). Then next spec.

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
- `get_state()`: return dict of all variable values

### CRITICAL: decide vs update boundary

The simulation calls these methods in this order:

    perception = env.build_perception(agent)          # no last_action_result
    action = model.decide(perception)                 # READ-ONLY — pick action from current state
    reward, result = env.apply(action)                # env executes the action
    new_perception = env.build_perception(agent)      # includes last_action_result
    model.update(action, reward, new_perception)      # WRITE — update all state here

`decide()` receives perception WITHOUT `last_action_result` (it is `{}`). \
Only `update()` receives the result of the action via `new_perception["last_action_result"]`.

Therefore:
- ALL state mutation (energy, drive, variables, learning) goes in `update()`.
- `decide()` ONLY reads `self.*` variables and perception to choose an action.
- If `decision_logic.pseudocode` in the spec mixes state updates with action selection, \
split them: state updates → `update()`, action selection → `decide()`.

Putting state updates in `decide()` WILL break the simulation. No exceptions.

## Test structure

- `from {formulation_id}_model import ClassName, Action` (PYTHONPATH is pre-configured)
- One test per `expected_behaviors[]` entry, guided by `test_pseudocode`
- Pure unit tests, no external dependencies beyond stdlib/math
- Seed random for determinism when model uses randomness

## Constraints

- Files must be self-contained (only stdlib/math/random imports).
- Use exact variable and parameter names from the spec.
- Implement ALL rules — never skip any.
"""

_MAX_ITERATIONS = 25
_MAX_TOKENS = 16384


class BuilderSubAgent:
    def __init__(self, *, client, reports_dir: Path, project_root: Path):
        self.client = client
        self.reports_dir = reports_dir
        self.tools = [READ_FILE_SCHEMA, WRITE_FILE_SCHEMA, RUN_TESTS_SCHEMA]
        self.registry = {
            "read_file": create_read_file(reports_dir),
            "write_file": create_write_file(reports_dir),
            "run_tests": create_run_tests(reports_dir, project_root),
        }

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

        response = await run_agent_loop(
            client=self.client,
            model="claude-sonnet-4-6",
            system=BUILDER_SUB_SYSTEM_PROMPT,
            tools=self.tools,
            messages=messages,
            registry=self.registry,
            max_iterations=_MAX_ITERATIONS,
            max_tokens=_MAX_TOKENS,
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        content = "\n".join(text_blocks)

        logger.info(
            "BuilderSubAgent finished for: %s (%d chars)",
            spec_id,
            len(content),
        )
        return content

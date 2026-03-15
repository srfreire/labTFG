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
You translate JSON agent specs into Python DecisionModel implementations and verify
them with tests.

## DecisionModel contract

The generated model must implement these three methods:

    def decide(self, perception: dict) -> Action
    def update(self, action: Action, reward: float, new_perception: dict) -> None
    def get_state(self) -> dict

Where `perception` is a dict with keys: x, y, grid_width, grid_height, step,
resources (dict of type → list of resource dicts), last_action_result (dict).

## Action dataclass

Define Action inline in each model file (do NOT import from external packages):

    @dataclass
    class Action:
        name: str
        params: dict = field(default_factory=dict)

## Process

For each JSON spec path provided:

1. Call `read_file` to read the JSON spec.
2. Implement the model class in `builder/{formulation_id}_model.py`:
   - `__init__`: initialize all variables (from `variables[]`) and parameters
     (from `parameters[]`) using their `initial_value`/`default` values.
   - `decide(perception)`: implement `decision_logic.pseudocode`, extracting
     perception fields as described in `env_mapping.perception_to_variables`.
   - `update(action, reward, new_perception)`: apply all `rules[]` to update
     internal state.
   - `get_state()`: return dict of all variable current values.
3. Write tests in `builder/test_{formulation_id}.py`:
   - Import the model class directly: `from {formulation_id}_model import ModelClassName, Action`
     (PYTHONPATH is set to `builder/` automatically when running tests).
   - One test per entry in `expected_behaviors[]`, using `test_pseudocode` as guide.
   - Tests are pure unit tests — instantiate the model, call decide/update, assert.
   - No external dependencies beyond stdlib and math.
4. Call `run_tests` on the test file.
5. If tests fail, read the error output, fix the code via `write_file`, and re-test.
   Maximum 3 fix attempts per spec. If still failing after 3 attempts, report the
   failure and move to the next spec.

## Constraints

- Each model file must be fully self-contained (Action defined inline, no external imports
  beyond stdlib/math/random).
- Use the exact variable names and parameter names from the JSON spec.
- Implement ALL rules from the spec — do not skip any.
- Tests must be deterministic where possible (seed random if the model uses randomness).
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

    async def run(self, paradigm_slug: str, spec_paths: list[str]) -> str:
        logger.info(
            "BuilderSubAgent starting — paradigm: %s, specs: %s",
            paradigm_slug,
            spec_paths,
        )
        spec_list = "\n".join(f"  - {p}" for p in spec_paths)
        messages = [
            {
                "role": "user",
                "content": (
                    f"Implement Python DecisionModel classes for paradigm: {paradigm_slug}\n"
                    f"Process each of the following JSON spec files:\n{spec_list}\n"
                    "For each spec: read it, implement the model, write tests, run them, "
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
            paradigm_slug,
            len(content),
        )
        return content

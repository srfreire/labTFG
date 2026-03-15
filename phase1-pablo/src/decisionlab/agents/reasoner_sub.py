"""ReasonerSubAgent — adapts mathematical formulations to a simulation environment."""

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

logger = logging.getLogger(__name__)

REASONER_SUB_SYSTEM_PROMPT = """\
You adapt mathematical formulations to a concrete simulation environment, producing \
structured JSON specs that a Builder agent will implement as Python code.

The Builder will create a Python class with `decide(perception) -> Action` and \
`update(action, reward, new_perception)` methods. The agent lives inside a grid-based \
simulation where the perception dict looks like:

```
{
  "x": int, "y": int,
  "grid_width": int, "grid_height": int,
  "step": int,
  "resources": {<type>: [{"x": int, "y": int, "type": str, ...properties from env_spec}]},
  "last_action_result": {<depends on action taken>}
}
```

Cross-reference this template with the actual env_spec you read — the env_spec is \
authoritative for available actions, resource types, and their properties.

## Process

1. Call `read_file` with path `deep/{slug}.md` to read the deep research report.
2. Call `read_file` with path `formulations/{slug}.md` to read all mathematical formulations.
3. Call `read_file` with path `env_spec.json` to read the simulation environment specification.
4. For *each* formulation, produce a JSON spec and call `write_file` to save it at \
`reasoner/{formulation_id}.json`.

### Deriving `formulation_id`

Combine the paradigm slug with a short descriptive slug derived from the formulation \
heading. Example: paradigm "homeostatic", formulation heading "PI Controller (Jacquier \
variant)" → `formulation_id` = `homeostatic_pi_controller`.

## Pseudocode style

Use Python-flavored pseudocode — you are bridging math to code. Write equations as \
assignment statements, NOT LaTeX:
- YES: `dF_dt = cF * intake - alphaF * F`
- NO: `\\frac{dF}{dt} = c_F \\cdot \\text{intake} - \\alpha_F \\cdot F`

## Differentiation

You have all formulations in context. Leverage this to ensure each JSON spec produces a \
genuinely distinct implementation — different state update logic, different decision \
strategies, different variable relationships. Do not produce near-duplicates.

## Constraints

- Ground every rule, parameter, and behavior in the literature cited in the deep report. \
Never fabricate references.
- Use ONLY actions listed in the env_spec. Do not invent actions that the environment \
does not support.
- Map ALL mathematical variables to concrete perception fields or internal state derived \
from perception fields. Every variable must be traceable to something the agent can observe \
or compute.
- Each JSON spec must be self-contained: the Builder should understand it without reading \
the other specs.

## JSON output schema (one file per formulation)

```json
{
  "formulation_id": "homeostatic_pi_controller",
  "paradigm": "homeostatic",
  "name": "Homeostatic PI Controller (Jacquier variant)",
  "description": "...",
  "variables": [
    {"symbol": "F", "name": "fat_reserves", "description": "Body fat reserves", \
"type": "float", "initial_value": 50.0, "range": [0, 100]}
  ],
  "parameters": [
    {"symbol": "cF", "name": "fat_conversion_rate", "default": 0.3, \
"source": "Jacquier et al., 2014"}
  ],
  "rules": [
    {"id": "R1", "description": "Fat reserves update", "type": "ODE", \
"pseudocode": "dF_dt = cF * intake - alphaF * F", "source_postulate": "P1"}
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
    {"id": "B1", "description": "Hunger increases without eating", \
"test_pseudocode": "run 100 steps without food → assert hunger increases"}
  ],
  "references": []
}
```

Follow this schema exactly. Every field is required.
"""

_MAX_ITERATIONS = 5
_MAX_TOKENS = 16384


class ReasonerSubAgent:
    def __init__(self, *, client, reports_dir: Path):
        self.client = client
        self.reports_dir = reports_dir
        self.tools = [READ_FILE_SCHEMA, WRITE_FILE_SCHEMA]
        self.registry = {
            "read_file": create_read_file(reports_dir),
            "write_file": create_write_file(reports_dir),
        }

    async def run(self, paradigm_slug: str) -> str:
        logger.info("ReasonerSubAgent starting — paradigm: %s", paradigm_slug)
        messages = [
            {
                "role": "user",
                "content": (
                    f"Produce structured JSON specs for the paradigm: {paradigm_slug}\n"
                    f"Read the deep report at: deep/{paradigm_slug}.md\n"
                    f"Read the formulations at: formulations/{paradigm_slug}.md\n"
                    f"Read the env spec at: env_spec.json"
                ),
            }
        ]

        response = await run_agent_loop(
            client=self.client,
            model="claude-opus-4-6",
            system=REASONER_SUB_SYSTEM_PROMPT,
            tools=self.tools,
            messages=messages,
            registry=self.registry,
            max_iterations=_MAX_ITERATIONS,
            max_tokens=_MAX_TOKENS,
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        content = "\n".join(text_blocks)

        logger.info(
            "ReasonerSubAgent finished for: %s (%d chars)",
            paradigm_slug,
            len(content),
        )
        return content

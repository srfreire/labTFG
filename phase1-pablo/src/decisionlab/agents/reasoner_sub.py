"""ReasonerSubAgent — adapts mathematical formulations to a simulation environment."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from decisionlab.config import SETTINGS
from decisionlab.runtime import agrex_context
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.files import (
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    create_read_file,
    create_write_file,
)

if TYPE_CHECKING:
    from shared.database import DatabaseService
    from shared.storage import StorageService

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
4. **Validate each formulation** before generating the spec (see Validation below).
5. For each **valid** formulation, produce a JSON spec and call `write_file` to save it at \
`reasoner/{paradigm_slug}/{formulation_slug}.json`.
6. For each **invalid** formulation, produce a validation report and call `write_file` to \
save it at `reasoner/{paradigm_slug}/{formulation_slug}.json` (same path, different schema).
7. After the final required `write_file` succeeds, stop calling tools and return a concise \
completion summary.

## Validation

Before generating the JSON spec for a formulation, critically analyze it for coherence:

1. **Variables used must be defined**: every variable referenced in equations and decision \
logic must appear in the Variables section of the formulation.
2. **No circular equations**: a variable's update rule must not depend on itself in a way \
that creates an unresolvable loop (differential equations like `dF/dt = f(F)` are fine — \
that is standard ODE form — but `F = F + g(F)` where `g` itself requires the new value \
of `F` is circular).
3. **Decision logic references existing constructs**: the decision rule must only reference \
variables and equations that are defined in the formulation.
4. **Parameters have reasonable defaults**: rates should not be 0 (would make the equation \
inert), counts and magnitudes should not be negative unless semantically justified.
5. **Env mapping is consistent**: actions_used must be a subset of the actions available in \
the env_spec; perception_to_variables must map to fields that exist in the perception template.

If ALL checks pass → proceed to generate the normal JSON spec.
If ANY check fails → write a **validation report** instead:

```json
{
  "formulation_id": "...",
  "paradigm": "...",
  "status": "invalid",
  "problems": [
    {"type": "undefined_variable", "detail": "Variable 'X' used in rule R2 but not defined in Variables section"},
    {"type": "circular_dependency", "detail": "Rule R1 defines F in terms of itself (not ODE form)"},
    {"type": "invalid_reference", "detail": "Decision logic references 'utility_score' but no such variable or rule exists"},
    {"type": "unreasonable_default", "detail": "Parameter 'decay_rate' has default 0, which makes rule R3 inert"},
    {"type": "inconsistent_mapping", "detail": "actions_used includes 'fly' but env_spec only supports up/down/left/right/stay/eat"},
    {"type": "other", "detail": "Free-text description of the problem"}
  ]
}
```

Be strict but fair: flag genuine incoherences, not stylistic preferences. If a formulation \
is mostly sound but has a minor issue, still flag it — the user will decide whether to \
rerun or accept.

### File naming

The user message provides `paradigm_slug` and optionally `formulation_slug` values. \
Use these EXACTLY as given for file paths:

- Save each spec at `reasoner/{paradigm_slug}/{formulation_slug}.json`
- Use `formulation_slug` as the `formulation_id` field in the JSON spec

If formulation slugs are provided, match them in order to the formulations in the .md \
(first slug → first formulation, etc.). Do not rename or transform them.

If no formulation slugs are provided, derive `formulation_slug` by slugifying the \
formulation heading (lowercase, hyphens for spaces, strip special chars).

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

_KNOWLEDGE_PROMPT_SECTION = """

## Knowledge Backbone

You have access to a knowledge backbone from past pipeline runs. Before adapting \
formulations to the environment, call `retrieve_knowledge` to find validated parameter \
ranges and env_mapping patterns from past runs. Use proven defaults and mapping \
strategies when available.
"""


class ReasonerSubAgent:
    def __init__(
        self,
        *,
        client,
        research_prefix: str,
        models_prefix: str,
        storage: StorageService,
        db: DatabaseService,
        run_id: str | None = None,
        knowledge_tool_schema: dict[str, Any] | None = None,
        knowledge_tool_handler: Callable[[dict], Awaitable[str]] | None = None,
    ):
        self.client = client
        self.tools: list[dict[str, Any]] = [READ_FILE_SCHEMA, WRITE_FILE_SCHEMA]
        # read from research prefix (deep reports, formulations, env_spec)
        # write to models prefix (reasoner specs)
        self.registry: dict[str, Callable[[dict], Awaitable[str]]] = {
            "read_file": create_read_file(
                research_prefix,
                storage=storage,
                fallback_prefixes=(models_prefix,),
            ),
            "write_file": create_write_file(
                models_prefix, storage=storage, db=db, run_id=run_id
            ),
        }

        self._has_knowledge = False
        if knowledge_tool_schema is not None and knowledge_tool_handler is not None:
            self.tools.append(knowledge_tool_schema)
            self.registry["retrieve_knowledge"] = knowledge_tool_handler
            self._has_knowledge = True

    async def run(
        self,
        paradigm_slug: str,
        formulation_slugs: list[str] | None = None,
    ) -> str:
        logger.info("ReasonerSubAgent starting — paradigm: %s", paradigm_slug)

        slug_instruction = ""
        if formulation_slugs:
            slug_list = "\n".join(f"  - {s}" for s in formulation_slugs)
            slug_instruction = (
                f"\n\nUse the following formulation slugs for the JSON specs "
                f"(one spec per slug, matched in order to the formulations in the .md)."
                f" Use each slug as the `formulation_id` field and for file naming "
                f"(`reasoner/{paradigm_slug}/{{slug}}.json`):\n{slug_list}"
            )

        messages = [
            {
                "role": "user",
                "content": (
                    f"Produce structured JSON specs for the paradigm: {paradigm_slug}\n"
                    f"Read the deep report at: deep/{paradigm_slug}.md\n"
                    f"Read the formulations at: formulations/{paradigm_slug}.md\n"
                    f"Read the env spec at: env_spec.json" + slug_instruction
                ),
            }
        ]

        system = REASONER_SUB_SYSTEM_PROMPT
        if self._has_knowledge:
            system += _KNOWLEDGE_PROMPT_SECTION

        parent_token = agrex_context.set_parent(
            agrex_context.trace_id("reasoner", paradigm_slug)
        )
        try:
            response = await run_agent_loop(
                client=self.client,
                model=SETTINGS.reasoner.model,
                system=system,
                tools=self.tools,
                messages=messages,
                registry=self.registry,
                max_iterations=SETTINGS.reasoner.max_iterations,
                max_tokens=SETTINGS.reasoner.max_tokens,
            )
        finally:
            agrex_context.reset_parent(parent_token)

        text_blocks = [b.text for b in response.content if b.type == "text"]
        content = "\n".join(text_blocks)

        logger.info(
            "ReasonerSubAgent finished for: %s (%d chars)",
            paradigm_slug,
            len(content),
        )
        return content

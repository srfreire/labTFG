"""
Architect agent — generates validated JSON environment specs from natural language.

Flow:
  1. Receives a natural language description of an environment
  2. Generates a JSON spec using Claude
  3. Validates the spec using the validate_spec tool
  4. Fixes errors if needed and re-validates
  5. Returns the validated JSON spec
"""

from __future__ import annotations

import json

from simlab.loop import Registry, run_agent_loop
from simlab.spec import validate_spec_dict
from simlab.utils import extract_text

# ---------------------------------------------------------------------------
# System prompt — tells Claude how to generate environment specs
# ---------------------------------------------------------------------------

ARCHITECT_SYSTEM_PROMPT = """\
You generate JSON environment specs for a 2D grid simulation lab.

Output ONLY valid JSON. No markdown. No explanation.

## Schema

{"grid": {"width": int, "height": int}, "actions": [Action], "resources": [Resource]}

Action: {"name": str, "effect": Effect}
Resource: {"type": str, "properties": dict, "count": int, "regenerate": bool}

## Effect types (only these three exist)

MoveEffect:    {"type": "MoveEffect", "dx": int, "dy": int}
ConsumeEffect: {"type": "ConsumeEffect", "resource_type": str, "reward": float}
NoopEffect:    {"type": "NoopEffect"}

All effects accept optional "reward": float (default 0.0).

## Constraints — violations cause errors

- Action names MUST be unique
- Resource types MUST be unique
- ConsumeEffect.resource_type MUST match a type in resources
- Grid width/height MUST be positive integers
- Property ranges: use [min, max] arrays (e.g. {"palatability": [0.1, 1.0]})

## Process — no exceptions

1. Generate the spec from the user's description
2. ALWAYS call validate_spec with the spec before returning
3. If validation fails: fix errors, call validate_spec again
4. Return ONLY the validated JSON

## Examples

Input: "Grid 10x10, food that regenerates, move 4 directions and eat"
Output:
{"grid": {"width": 10, "height": 10}, "actions": [{"name": "move_up", "effect": {"type": "MoveEffect", "dx": 0, "dy": -1}}, {"name": "move_down", "effect": {"type": "MoveEffect", "dx": 0, "dy": 1}}, {"name": "move_left", "effect": {"type": "MoveEffect", "dx": -1, "dy": 0}}, {"name": "move_right", "effect": {"type": "MoveEffect", "dx": 1, "dy": 0}}, {"name": "eat", "effect": {"type": "ConsumeEffect", "resource_type": "food", "reward": 1.0}}], "resources": [{"type": "food", "properties": {}, "count": 5, "regenerate": true}]}

Input: "20x20, food (palatability 0.1-1.0, 5 units) and water (3 units, no regen), move + eat + drink + rest"
Output:
{"grid": {"width": 20, "height": 20}, "actions": [{"name": "move_up", "effect": {"type": "MoveEffect", "dx": 0, "dy": -1}}, {"name": "move_down", "effect": {"type": "MoveEffect", "dx": 0, "dy": 1}}, {"name": "move_left", "effect": {"type": "MoveEffect", "dx": -1, "dy": 0}}, {"name": "move_right", "effect": {"type": "MoveEffect", "dx": 1, "dy": 0}}, {"name": "eat", "effect": {"type": "ConsumeEffect", "resource_type": "food", "reward": 1.0}}, {"name": "drink", "effect": {"type": "ConsumeEffect", "resource_type": "water", "reward": 1.0}}, {"name": "rest", "effect": {"type": "NoopEffect"}}], "resources": [{"type": "food", "properties": {"palatability": [0.1, 1.0]}, "count": 5, "regenerate": true}, {"type": "water", "properties": {}, "count": 3, "regenerate": false}]}

## Knowledge context usage

When a "## Knowledge context" section is present in the user message, use it \
to generate a more scientifically grounded environment:

### Paradigm facts
Use postulates and key properties to choose appropriate resources, actions, and \
grid dimensions. E.g., if the paradigm postulates homeostatic regulation with \
multiple drives, include multiple resource types with varying palatability.

### Previous environments
Reuse grid dimensions, resource types, and action sets that worked in previous \
simulations of the same paradigm. Adjust counts or properties as needed for the \
current request, but maintain consistency with proven configurations.

### Formulations
Use the mathematical model to dimension rewards and resource properties. E.g., \
if the model uses logarithmic utility, provide a wide reward range; if it uses \
binary signals, keep rewards at 0/1.

If knowledge context is empty or absent, generate the spec from scratch based \
solely on the user description.
"""


# ---------------------------------------------------------------------------
# Validation tool — the Architect calls this to check its own output
# ---------------------------------------------------------------------------

VALIDATE_SPEC_TOOL = {
    "name": "validate_spec",
    "description": "Validate a JSON environment spec. Call this with your generated spec before returning it.",
    "input_schema": {
        "type": "object",
        "properties": {
            "spec": {
                "type": "object",
                "description": "The environment spec to validate",
            },
        },
        "required": ["spec"],
    },
}

DEFAULT_MODEL = "anthropic/claude-haiku-4-5"


async def _validate_spec_tool(params: dict) -> str:
    """Tool implementation: validate a spec and return errors if any."""
    errors = validate_spec_dict(params.get("spec", {}))
    if errors:
        return json.dumps({"valid": False, "errors": errors})
    return json.dumps({"valid": True})


ARCHITECT_REGISTRY: Registry = {
    "validate_spec": _validate_spec_tool,
}


# ---------------------------------------------------------------------------
# Architect class
# ---------------------------------------------------------------------------


class Architect:
    def __init__(self, *, client, model: str = DEFAULT_MODEL):
        self.client = client
        self.model = model
        self.tools = [VALIDATE_SPEC_TOOL]
        self.registry = ARCHITECT_REGISTRY

    async def run(
        self,
        prompt: str,
        *,
        max_iterations: int = 10,
        on_tool_call=None,
        extra_tools: list[dict] | None = None,
        extra_registry: dict | None = None,
        prompt_suffix: str = "",
        knowledge_context: str = "",
    ) -> str:
        tools = self.tools + (extra_tools or [])
        registry = {**self.registry, **(extra_registry or {})}
        system = ARCHITECT_SYSTEM_PROMPT + prompt_suffix
        parts = [prompt]
        if knowledge_context:
            parts.append(knowledge_context)
        user_content = "\n\n".join(parts)
        response = await run_agent_loop(
            client=self.client,
            model=self.model,
            system=system,
            tools=tools,
            messages=[{"role": "user", "content": user_content}],
            registry=registry,
            max_iterations=max_iterations,
            on_tool_call=on_tool_call,
        )
        return extract_text(response)

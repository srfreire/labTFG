"""Architect agent — generates validated JSON environment specs from natural language."""
from __future__ import annotations

import json

from simlab.runtime import run_agent_loop, Registry
from simlab.spec import validate_spec_dict

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
"""

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

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"


async def _validate_spec_tool(params: dict) -> str:
    """Tool function for the agent loop registry."""
    errors = validate_spec_dict(params.get("spec", {}))
    if errors:
        return json.dumps({"valid": False, "errors": errors})
    return json.dumps({"valid": True})


ARCHITECT_REGISTRY: Registry = {
    "validate_spec": _validate_spec_tool,
}


class Architect:
    """Architect agent — interprets natural language and produces environment specs."""

    def __init__(self, *, client, model: str = DEFAULT_MODEL):
        self.client = client
        self.model = model
        self.tools = [VALIDATE_SPEC_TOOL]
        self.registry = ARCHITECT_REGISTRY

    async def run(self, prompt: str, *, max_iterations: int = 10) -> str:
        """Generate a validated JSON environment spec from a natural language prompt."""
        response = await run_agent_loop(
            client=self.client,
            model=self.model,
            system=ARCHITECT_SYSTEM_PROMPT,
            tools=self.tools,
            messages=[{"role": "user", "content": prompt}],
            registry=self.registry,
            max_iterations=max_iterations,
        )

        text = next((b.text for b in response.content if b.type == "text"), "")
        return _strip_markdown_fences(text)


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` fences if the LLM wraps the output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped

"""Architect agent — generates validated JSON environment specs from natural language."""
from __future__ import annotations

import json
import logging

import anthropic

from simlab.spec import validate_spec_dict

logger = logging.getLogger(__name__)

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


def _dispatch_tool(name: str, input_data: dict) -> str:
    """Execute a tool call and return the result as a string."""
    if name == "validate_spec":
        errors = validate_spec_dict(input_data.get("spec", {}))
        if errors:
            return json.dumps({"valid": False, "errors": errors})
        return json.dumps({"valid": True})
    return json.dumps({"error": f"Unknown tool: {name}"})


async def run_architect(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    max_iterations: int = 10,
) -> str:
    """Run the Architect agent and return the generated JSON spec as a string."""
    client = anthropic.AsyncAnthropic()
    messages = [{"role": "user", "content": prompt}]

    for iteration in range(max_iterations):
        logger.info("Architect iteration %d/%d", iteration + 1, max_iterations)
        response = await client.messages.create(
            model=model,
            system=ARCHITECT_SYSTEM_PROMPT,
            tools=[VALIDATE_SPEC_TOOL],
            messages=messages,
            max_tokens=4096,
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if b.type == "text"), "")
            return text

        if response.stop_reason != "tool_use":
            text = next((b.text for b in response.content if b.type == "text"), "")
            return text

        # Process tool calls
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tc in tool_calls:
            result = _dispatch_tool(tc.name, tc.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result,
            })
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError(f"Architect exceeded max iterations ({max_iterations})")

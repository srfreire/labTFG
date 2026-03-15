"""Architect agent — generates validated JSON environment specs from natural language."""
from __future__ import annotations

import json

from claude_agent_sdk import (
    tool,
    create_sdk_mcp_server,
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

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


@tool("validate_spec", "Validate a JSON environment spec", {"spec": dict})
async def validate_spec_tool(args):
    """MCP tool wrapper around validate_spec_dict."""
    spec = args["spec"]
    errors = validate_spec_dict(spec)
    if errors:
        result = {"valid": False, "errors": errors}
    else:
        result = {"valid": True}
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


_mcp_server = create_sdk_mcp_server("architect-tools", tools=[validate_spec_tool])


async def run_architect(prompt: str, max_turns: int = 10) -> str:
    """Run the Architect agent and return the generated JSON spec as a string."""
    options = ClaudeAgentOptions(
        mcp_servers={"architect": _mcp_server},
        system_prompt=ARCHITECT_SYSTEM_PROMPT,
        max_turns=max_turns,
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        result = ""
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                result = message.result
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result = block.text
        return result

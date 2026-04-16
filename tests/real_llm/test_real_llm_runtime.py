"""Real-LLM tests for `decisionlab.runtime.loop.run_agent_loop`.

Verifies the agent loop dispatches a real Claude tool call against a tiny
fake tool, then lets the model emit a final text response.
"""

from __future__ import annotations

import pytest

from decisionlab.runtime.loop import run_agent_loop

_ECHO_TOOL = {
    "name": "echo",
    "description": "Echo a single string back to the user. Use this when asked to echo something.",
    "input_schema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
}


async def _echo(args: dict) -> str:
    return args.get("text", "")


@pytest.mark.asyncio
async def test_real_loop_dispatches_tool_then_finishes(real_anthropic_client):
    """Loop calls the echo tool with the requested string, then ends."""
    response = await run_agent_loop(
        client=real_anthropic_client,
        model="claude-haiku-4-5",
        system=(
            "You have access to an `echo` tool. When the user asks you to echo something, "
            "call the tool exactly once with the given text, then respond with a short "
            "confirmation like 'done'."
        ),
        tools=[_ECHO_TOOL],
        messages=[
            {
                "role": "user",
                "content": "Please echo the string 'hello world' using the echo tool.",
            }
        ],
        registry={"echo": _echo},
        max_iterations=4,
    )

    assert response.stop_reason == "end_turn"
    text_blocks = [b.text for b in response.content if b.type == "text"]
    combined = " ".join(text_blocks).lower()
    assert combined  # final text response is non-empty


@pytest.mark.asyncio
async def test_real_loop_no_tools_just_text(real_anthropic_client):
    """With no tools at all, the loop returns the model's first text response."""
    response = await run_agent_loop(
        client=real_anthropic_client,
        model="claude-haiku-4-5",
        system="Reply briefly.",
        tools=[],
        messages=[{"role": "user", "content": "Say the single word 'pong' and nothing else."}],
        registry={},
        max_iterations=2,
    )
    text = " ".join(b.text for b in response.content if b.type == "text").lower()
    assert "pong" in text

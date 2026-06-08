"""
Agentic loop — the core execution engine for all agents.

Flow:
  1. Send messages + tools to Claude
  2. If Claude responds with text → done, return response
  3. If Claude requests tool calls → execute them in order
  4. Append results to conversation and go back to step 1
  5. Repeat until done or max iterations reached
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# A tool function: receives input dict, returns result string
ToolFunction = Callable[[dict], Awaitable[str]]

# Maps tool name → its implementation function
Registry = dict[str, ToolFunction]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------


async def _execute_single_tool(call, registry: Registry) -> dict[str, Any]:
    """Run one tool call and return a tool_result block for the API."""
    if call.name not in registry:
        msg = f"Unknown tool '{call.name}'. Available: {list(registry)}"
        logger.error(msg)
        return {
            "type": "tool_result",
            "tool_use_id": call.id,
            "content": msg,
            "is_error": True,
        }

    try:
        logger.info("Calling tool '%s'", call.name)
        result = await registry[call.name](call.input)
        logger.info("Tool '%s' returned (%d chars)", call.name, len(result))
        return {"type": "tool_result", "tool_use_id": call.id, "content": result}
    except Exception as e:
        logger.error(
            "Tool '%s' raised %s: %s", call.name, type(e).__name__, e, exc_info=True
        )
        return {
            "type": "tool_result",
            "tool_use_id": call.id,
            "content": f"[{type(e).__name__}] {e}",
            "is_error": True,
        }


async def dispatch_tools(tool_calls: list, registry: Registry) -> list[dict[str, Any]]:
    """Execute tool calls in request order and collect results."""
    results = []
    for call in tool_calls:
        results.append(await _execute_single_tool(call, registry))
    return results


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------


async def run_agent_loop(
    *,
    client,
    model: str,
    system: str,
    tools: list[dict],
    messages: list[dict[str, Any]],
    registry: Registry,
    max_tokens: int = 4096,
    max_iterations: int = 20,
    on_tool_call: Callable[[str], Awaitable[None]] | None = None,
) -> Any:
    """
    Run a tool-use loop until the agent finishes or hits max_iterations.

    Each iteration:
      - Calls Claude with the current conversation
      - If Claude is done talking (end_turn) → return the response
      - If Claude wants to use tools → execute them, add results, loop again
    """
    messages = list(messages)  # don't mutate the caller's list

    for iteration in range(1, max_iterations + 1):
        logger.info("Iteration %d/%d — calling %s", iteration, max_iterations, model)

        # Step 1: Ask Claude
        response = await client.messages.create(
            model=model,
            system=system,
            tools=tools,
            messages=messages,
            max_tokens=max_tokens,
            cache_control={"type": "ephemeral"},
        )

        # Step 2: Claude is done → return
        if response.stop_reason == "end_turn":
            logger.info("Agent finished after %d iteration(s)", iteration)
            return response

        # Unexpected stop reason → return as-is
        if response.stop_reason != "tool_use":
            logger.warning(
                "Unexpected stop_reason '%s' on iteration %d",
                response.stop_reason,
                iteration,
            )
            return response

        # Step 3: Claude wants tools → extract, execute, append results
        tool_calls = [block for block in response.content if block.type == "tool_use"]
        if not tool_calls:
            logger.warning(
                "stop_reason='tool_use' but no tool_use blocks on iteration %d",
                iteration,
            )
            return response

        messages.append({"role": "assistant", "content": response.content})
        if on_tool_call:
            for call in tool_calls:
                await on_tool_call(call.name)
        results = await dispatch_tools(tool_calls, registry)
        messages.append({"role": "user", "content": results})

    raise RuntimeError(f"Agent did not finish within {max_iterations} iterations")

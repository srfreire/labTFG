from __future__ import annotations

import logging
from typing import Any

from decisionlab.runtime.dispatcher import Registry, dispatch_tools

logger = logging.getLogger(__name__)


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
) -> Any:
    messages = list(messages)

    for iteration in range(max_iterations):
        response = await client.messages.create(
            model=model,
            system=system,
            tools=tools,
            messages=messages,
            max_tokens=max_tokens,
        )

        if response.stop_reason == "end_turn":
            return response

        if response.stop_reason != "tool_use":
            logger.warning(
                "Unexpected stop_reason '%s' on iteration %d, returning response as-is",
                response.stop_reason, iteration + 1,
            )
            return response

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if not tool_calls:
            logger.warning("stop_reason='tool_use' but no tool_use blocks on iteration %d", iteration + 1)
            return response

        messages.append({"role": "assistant", "content": response.content})

        results = await dispatch_tools(tool_calls, registry)
        messages.append({"role": "user", "content": results})

    raise RuntimeError(f"Max iterations ({max_iterations}) reached")

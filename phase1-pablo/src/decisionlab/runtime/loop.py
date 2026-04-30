from __future__ import annotations

import logging
from typing import Any

from decisionlab.runtime.dispatcher import Registry, dispatch_tools
from decisionlab.runtime.usage import record as record_usage

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

    # Streaming is only required when ``max_tokens`` could push the request
    # past the SDK's non-streaming 10-minute timeout guard. Below 24k all
    # in-tree stages run safely with ``messages.create`` (matches what's been
    # in production for Formalizer/Reasoner/Builder at 16384). Above that —
    # currently only Researcher at 32k — fall through to streaming.
    use_stream = max_tokens >= 24000

    for iteration in range(max_iterations):
        logger.info(
            "Loop iteration %d/%d — calling %s", iteration + 1, max_iterations, model
        )
        if use_stream:
            async with client.messages.stream(
                model=model,
                system=system,
                tools=tools,
                messages=messages,
                max_tokens=max_tokens,
                cache_control={"type": "ephemeral"},
            ) as stream:
                response = await stream.get_final_message()
        else:
            response = await client.messages.create(
                model=model,
                system=system,
                tools=tools,
                messages=messages,
                max_tokens=max_tokens,
                cache_control={"type": "ephemeral"},
            )
        record_usage(model, getattr(response, "usage", None))

        if response.stop_reason == "end_turn":
            logger.info(
                "Agent finished (end_turn) after %d iteration(s)", iteration + 1
            )
            return response

        if response.stop_reason == "max_tokens":
            usage = getattr(response, "usage", None)
            out_tokens = getattr(usage, "output_tokens", None) if usage else None
            raise RuntimeError(
                f"Agent loop hit max_tokens={max_tokens} on iteration {iteration + 1} "
                f"(output_tokens={out_tokens}); raise max_tokens or split work"
            )

        if response.stop_reason != "tool_use":
            logger.warning(
                "Unexpected stop_reason '%s' on iteration %d, returning response as-is",
                response.stop_reason,
                iteration + 1,
            )
            return response

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if not tool_calls:
            logger.warning(
                "stop_reason='tool_use' but no tool_use blocks on iteration %d",
                iteration + 1,
            )
            return response

        messages.append({"role": "assistant", "content": response.content})

        results = await dispatch_tools(tool_calls, registry)
        messages.append({"role": "user", "content": results})

    raise RuntimeError(f"Max iterations ({max_iterations}) reached")

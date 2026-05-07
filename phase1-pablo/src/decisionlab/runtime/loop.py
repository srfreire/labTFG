from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from typing import Any

from decisionlab.runtime.dispatcher import Registry, dispatch_tools
from decisionlab.runtime.tool_calls import record_loop_cap_reached
from decisionlab.runtime.usage import record as record_usage

logger = logging.getLogger(__name__)

# How much of the first user message to keep in the cap-hit trace event.
# Long enough to identify which topic blew the cap, short enough not to
# bloat report.json when this fires across many topics in an eval.
_TOPIC_EXCERPT_CHARS = 200


def _extract_topic_excerpt(messages: list[dict[str, Any]]) -> str:
    """Pull a short, identifying excerpt from the loop's first user message.

    The Researcher / DeepResearcher / Formalizer all prefix their first user
    message with the topic or paradigm slug, so the leading slice of
    ``messages[0]['content']`` is enough to disambiguate cap-hit traces in
    the report. Handles both string content and Anthropic block-list content.
    """
    if not messages:
        return ""
    content = messages[0].get("content", "")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = " ".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    else:
        text = str(content)
    text = text.strip()
    if len(text) > _TOPIC_EXCERPT_CHARS:
        return text[:_TOPIC_EXCERPT_CHARS] + "…"
    return text


def _hash_tool_args(args: object) -> str:
    """Same 12-char hash convention as ``runtime.tool_calls.record``."""
    try:
        blob = json.dumps(args, sort_keys=True, default=str).encode()
    except (TypeError, ValueError):
        blob = repr(args).encode()
    return hashlib.md5(blob, usedforsecurity=False).hexdigest()[:12]


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

    # Ring buffer of the last 2 iterations' tool_use shapes — surfaced via
    # ``record_loop_cap_reached`` when the loop exhausts ``max_iterations``.
    # Phase F observed cap-hits on 4/12 topics; this captures *what* the
    # model was still trying to do at the cap so we can decide whether to
    # raise the cap, fix the prompt, or both.
    recent_tool_uses: deque[list[dict]] = deque(maxlen=2)

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

        recent_tool_uses.append(
            [
                {"name": b.name, "args_hash": _hash_tool_args(b.input)}
                for b in tool_calls
            ]
        )

        messages.append({"role": "assistant", "content": response.content})

        results = await dispatch_tools(tool_calls, registry)
        messages.append({"role": "user", "content": results})

    # Cap exhausted without ``end_turn`` — emit a structured trace event
    # (no-op when no recording session is active) before raising. The
    # event lands in the same ``tool_call_log`` the eval runner already
    # serializes to ``report.json``, so analysis can locate cap-hit
    # topics + their last-attempted tool calls without re-running.
    record_loop_cap_reached(
        topic_excerpt=_extract_topic_excerpt(messages),
        last_tool_uses=list(recent_tool_uses),
        max_iterations=max_iterations,
    )

    raise RuntimeError(f"Max iterations ({max_iterations}) reached")

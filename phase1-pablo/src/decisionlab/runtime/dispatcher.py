from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from decisionlab.runtime.agrex_context import trace_tool_done, trace_tool_start
from decisionlab.runtime.tool_calls import record as record_tool_call

logger = logging.getLogger(__name__)

ToolFunction = Callable[[dict], Awaitable[str]]
Registry = dict[str, ToolFunction]


async def dispatch_tools(tool_calls: list, registry: Registry) -> list[dict[str, Any]]:
    async def run_one(call) -> dict[str, Any]:
        trace_id = await trace_tool_start(call.name, call.input)
        if call.name not in registry:
            msg = f"Unknown tool '{call.name}'. Available: {list(registry)}"
            logger.error(msg)
            record_tool_call(call.name, call.input, succeeded=False, duration_ms=0.0)
            await trace_tool_done(trace_id, succeeded=False, error=msg, duration_ms=0.0)
            return {
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": msg,
                "is_error": True,
            }
        t0 = time.monotonic_ns()
        succeeded = False
        duration_ms: float | None = None
        try:
            logger.info("Calling tool '%s'", call.name)
            result = await registry[call.name](call.input)
            logger.info("Tool '%s' returned (%d chars)", call.name, len(result))
            succeeded = True
            duration_ms = (time.monotonic_ns() - t0) / 1_000_000
            await trace_tool_done(
                trace_id,
                succeeded=True,
                output=result,
                duration_ms=duration_ms,
            )
            return {"type": "tool_result", "tool_use_id": call.id, "content": result}
        except Exception as e:
            logger.error(
                "Tool '%s' (call_id=%s) raised %s: %s",
                call.name,
                call.id,
                type(e).__name__,
                e,
            )
            duration_ms = (time.monotonic_ns() - t0) / 1_000_000
            await trace_tool_done(
                trace_id,
                succeeded=False,
                error=e,
                duration_ms=duration_ms,
            )
            return {
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": f"[{type(e).__name__}] {e}",
                "is_error": True,
            }
        finally:
            if duration_ms is None:
                duration_ms = (time.monotonic_ns() - t0) / 1_000_000
            record_tool_call(
                call.name, call.input, succeeded=succeeded, duration_ms=duration_ms
            )

    return list(await asyncio.gather(*(run_one(call) for call in tool_calls)))

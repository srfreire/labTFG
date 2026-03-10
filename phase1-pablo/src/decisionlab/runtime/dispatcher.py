from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

ToolFunction = Callable[[dict], Awaitable[str]]
Registry = dict[str, ToolFunction]


async def dispatch_tools(tool_calls: list, registry: Registry) -> list[dict[str, Any]]:
    async def run_one(call) -> dict[str, Any]:
        if call.name not in registry:
            msg = f"Unknown tool '{call.name}'. Available: {list(registry)}"
            logger.error(msg)
            return {"type": "tool_result", "tool_use_id": call.id, "content": msg, "is_error": True}
        try:
            logger.info("Calling tool '%s'", call.name)
            result = await registry[call.name](call.input)
            logger.info("Tool '%s' returned (%d chars)", call.name, len(result))
            return {"type": "tool_result", "tool_use_id": call.id, "content": result}
        except Exception as e:
            logger.error("Tool '%s' (call_id=%s) raised %s: %s", call.name, call.id, type(e).__name__, e)
            return {"type": "tool_result", "tool_use_id": call.id, "content": f"[{type(e).__name__}] {e}", "is_error": True}

    return list(await asyncio.gather(*(run_one(call) for call in tool_calls)))

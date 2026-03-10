from __future__ import annotations

import asyncio
from typing import Any, Callable, Awaitable


ToolFunction = Callable[[dict], Awaitable[str]]
Registry = dict[str, ToolFunction]


async def dispatch_tools(tool_calls: list, registry: Registry) -> list[dict[str, Any]]:
    async def run_one(call) -> dict[str, Any]:
        try:
            result = await registry[call.name](call.input)
            return {"type": "tool_result", "tool_use_id": call.id, "content": result}
        except Exception as e:
            return {"type": "tool_result", "tool_use_id": call.id, "content": str(e), "is_error": True}

    return list(await asyncio.gather(*(run_one(call) for call in tool_calls)))

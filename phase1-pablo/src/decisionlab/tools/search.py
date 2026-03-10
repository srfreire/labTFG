from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Awaitable, Callable

from decisionlab.domain.ports import WebSearchPort

WEB_SEARCH_SCHEMA: dict[str, Any] = {
    "name": "web_search",
    "description": "Search the web for information about decision-making paradigms. Returns a list of results with title, URL, and snippet.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    },
}


def create_web_search(adapter: WebSearchPort) -> Callable[[dict], Awaitable[str]]:
    async def web_search(params: dict) -> str:
        if "query" not in params:
            raise ValueError("web_search requires 'query' parameter")
        results = await adapter.search(params["query"])
        return json.dumps([asdict(r) for r in results], indent=2)
    return web_search

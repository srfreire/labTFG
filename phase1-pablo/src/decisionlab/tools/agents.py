from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

LAUNCH_DEEP_RESEARCH_SCHEMA: dict[str, Any] = {
    "name": "launch_deep_research",
    "description": "Launch a sub-agent to deeply research a specific decision-making paradigm. Returns a concise summary; the full report is saved to disk.",
    "input_schema": {
        "type": "object",
        "properties": {
            "paradigm": {
                "type": "string",
                "description": "Short paradigm name only (e.g. 'Homeostatic regulation', 'Q-Learning'). Do NOT include descriptions or references — the sub-agent will find those itself.",
            },
        },
        "required": ["paradigm"],
    },
}


SubAgentFactory = Callable[[str], Awaitable[str]]


def create_launch_deep_research(
    factory: SubAgentFactory,
) -> Callable[[dict], Awaitable[str]]:
    async def launch_deep_research(params: dict) -> str:
        if "paradigm" not in params:
            raise ValueError("launch_deep_research requires 'paradigm' parameter")
        return await factory(params["paradigm"])

    return launch_deep_research

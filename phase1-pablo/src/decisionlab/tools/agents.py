from __future__ import annotations

from typing import Any, Awaitable, Callable

LAUNCH_DEEP_RESEARCH_SCHEMA: dict[str, Any] = {
    "name": "launch_deep_research",
    "description": "Launch a sub-agent to deeply research a specific decision-making paradigm. The sub-agent will search for papers, read abstracts, and produce a detailed markdown report. Use this for each paradigm you identify.",
    "input_schema": {
        "type": "object",
        "properties": {
            "paradigm": {
                "type": "string",
                "description": "Name and brief description of the paradigm to research in depth",
            },
        },
        "required": ["paradigm"],
    },
}


SubAgentFactory = Callable[[str], Awaitable[str]]


def create_launch_deep_research(factory: SubAgentFactory) -> Callable[[dict], Awaitable[str]]:
    async def launch_deep_research(params: dict) -> str:
        return await factory(params["paradigm"])
    return launch_deep_research

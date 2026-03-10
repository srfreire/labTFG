"""Researcher agent — discovers and investigates decision-making paradigms."""

from __future__ import annotations

import logging

from decisionlab.agents.deep_researcher import DeepResearcher
from decisionlab.domain.models import ResearchReport
from decisionlab.domain.ports import WebSearchPort
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.agents import LAUNCH_DEEP_RESEARCH_SCHEMA, create_launch_deep_research
from decisionlab.tools.search import WEB_SEARCH_SCHEMA, create_web_search

logger = logging.getLogger(__name__)

RESEARCHER_SYSTEM_PROMPT = """\
You discover decision-making paradigms for a given problem. You MUST be efficient with tool calls.

## Process

1. Run 2-3 web searches with different angles to discover paradigms.
2. From results, identify the distinct paradigms (a coherent theoretical framework with its own assumptions, variables, and mechanisms).
3. Call launch_deep_research ONCE per paradigm — do NOT investigate paradigms yourself.
4. After all deep research returns, produce your final summary. Do NOT search again.

## Constraints

- Maximum 3 web searches total. Make them count.
- Only cite authors/papers found in search results. Never fabricate.
- Once you have launched deep research for all paradigms, STOP searching and write the summary.

## Output format

# Decision-making paradigms: {problem}

## 1. {Paradigm name}
{One-line description}
**Key authors**: {from search results}
**Key concepts**: {list}

## 2. {Paradigm name}
...
"""

_MAX_ITERATIONS = 10


class Researcher:
    def __init__(self, *, client, search: WebSearchPort):
        self.client = client
        self.search = search

        self._deep_reports: dict[str, str] = {}

        self.tools = [WEB_SEARCH_SCHEMA, LAUNCH_DEEP_RESEARCH_SCHEMA]
        self.registry = {
            "web_search": create_web_search(search),
            "launch_deep_research": create_launch_deep_research(self._run_deep_research),
        }

    async def _run_deep_research(self, paradigm: str) -> str:
        logger.info("Launching DeepResearcher for paradigm: %s", paradigm)
        dr = DeepResearcher(client=self.client, search=self.search)
        report = await dr.run(paradigm)
        self._deep_reports[paradigm] = report
        logger.info("DeepResearcher finished for: %s (%d chars)", paradigm, len(report))
        return report

    async def run(self, problem: str) -> ResearchReport:
        self._deep_reports.clear()
        logger.info("Researcher starting — problem: %s", problem)

        messages = [{"role": "user", "content": problem}]

        response = await run_agent_loop(
            client=self.client,
            model="claude-sonnet-4-6",
            system=RESEARCHER_SYSTEM_PROMPT,
            tools=self.tools,
            messages=messages,
            registry=self.registry,
            max_iterations=_MAX_ITERATIONS,
        )

        summary = "\n".join(b.text for b in response.content if b.type == "text")
        if not summary.strip():
            logger.warning("Researcher produced empty summary for problem: %s", problem)

        # TODO: parse paradigms from LLM summary text into structured Paradigm objects
        return ResearchReport(
            paradigms=[],
            summary=summary,
            deep_reports=dict(self._deep_reports),
        )

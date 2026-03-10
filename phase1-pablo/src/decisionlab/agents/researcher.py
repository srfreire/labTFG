"""Researcher agent — discovers and investigates decision-making paradigms."""

from __future__ import annotations

import logging

from decisionlab.agents.deep_researcher import DeepResearcher

logger = logging.getLogger(__name__)
from decisionlab.domain.models import ResearchReport
from decisionlab.domain.ports import PaperSearchPort, WebSearchPort
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.agents import LAUNCH_DEEP_RESEARCH_SCHEMA, create_launch_deep_research
from decisionlab.tools.search import (
    SEARCH_PAPERS_SCHEMA,
    WEB_SEARCH_SCHEMA,
    create_search_papers,
    create_web_search,
)

RESEARCHER_SYSTEM_PROMPT = """\
You are a decision-making paradigm researcher. Your job: given a decision-making problem, discover ALL relevant scientific paradigms through breadth-first search.

## Process

1. SEARCH BROADLY — Use web_search and search_papers with varied queries to discover paradigms. Cast a wide net: try synonyms, related fields, different theoretical frameworks.

2. IDENTIFY PARADIGMS — From search results, identify distinct decision-making paradigms. A paradigm is a coherent theoretical framework with its own assumptions, variables, and mechanisms (e.g., "homeostatic regulation", "Q-learning", "prospect theory").

3. LAUNCH DEEP RESEARCH — For each identified paradigm, call launch_deep_research with a clear description. Do NOT research paradigms yourself in depth — delegate.

4. EVALUATE COVERAGE — After receiving sub-agent results, assess:
   - Are there paradigm families not yet covered?
   - Did search results hint at paradigms not yet investigated?
   - Are the found paradigms sufficiently diverse?
   If coverage is insufficient, search more and launch additional sub-agents.

5. PRODUCE SUMMARY — When satisfied with coverage, produce a final summary listing all discovered paradigms with: name, one-line description, key authors, and key concepts.

## Rules

- BREADTH over depth. You identify, sub-agents investigate.
- Minimum 3 varied search queries before concluding no more paradigms exist.
- Always cite real authors and papers from search results. Never fabricate references.
- If search results are poor, reformulate queries — do not give up after one attempt.

## Output format

Return your final summary as structured text:

# Decision-making paradigms: {problem}

## 1. {Paradigm name}
{One-line description}
**Key authors**: {from search results}
**Key concepts**: {list}

## 2. {Paradigm name}
...
"""


class Researcher:
    def __init__(self, *, client, search: WebSearchPort, papers: PaperSearchPort):
        self.client = client
        self.search = search
        self.papers = papers

        self._deep_reports: dict[str, str] = {}

        self.tools = [WEB_SEARCH_SCHEMA, SEARCH_PAPERS_SCHEMA, LAUNCH_DEEP_RESEARCH_SCHEMA]
        self.registry = {
            "web_search": create_web_search(search),
            "search_papers": create_search_papers(papers),
            "launch_deep_research": create_launch_deep_research(self._run_deep_research),
        }

    async def _run_deep_research(self, paradigm: str) -> str:
        dr = DeepResearcher(client=self.client, search=self.search, papers=self.papers)
        report = await dr.run(paradigm)
        self._deep_reports[paradigm] = report
        return report

    async def run(self, problem: str) -> ResearchReport:
        self._deep_reports.clear()

        messages = [{"role": "user", "content": problem}]

        response = await run_agent_loop(
            client=self.client,
            model="claude-sonnet-4-6",
            system=RESEARCHER_SYSTEM_PROMPT,
            tools=self.tools,
            messages=messages,
            registry=self.registry,
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

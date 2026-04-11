"""Researcher agent — discovers and investigates decision-making paradigms."""

from __future__ import annotations

import logging
from pathlib import Path

from decisionlab.agents.deep_researcher import DeepResearcher
from decisionlab.domain.models import Paradigm, ResearchReport
from decisionlab.domain.ports import WebSearchPort
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.agents import LAUNCH_DEEP_RESEARCH_SCHEMA, create_launch_deep_research
from decisionlab.tools.reports import (
    READ_REPORT_SCHEMA,
    create_read_report,
    save_summary_report,
    slugify,
)
from decisionlab.tools.search import WEB_SEARCH_SCHEMA, create_web_search

logger = logging.getLogger(__name__)

RESEARCHER_SYSTEM_PROMPT = """\
You discover decision-making paradigms for a given problem.

Each paradigm you find will later be mathematically formalized and implemented as an \
autonomous agent in a grid-based simulation. Only select paradigms that have quantifiable \
variables, causal mechanisms, and can plausibly drive an agent's action selection.

## Process

1. Run 2-3 web searches with different angles (e.g., biological, psychological, \
computational/RL, economic) to discover paradigms from diverse traditions.
2. Identify distinct paradigms — each must be a coherent theoretical framework with its \
own assumptions, measurable variables, and decision mechanisms.
3. Call `launch_deep_research` ONCE per paradigm. Each call returns a concise summary.
4. After all deep research returns, STOP searching.
5. Use `read_report` for EVERY paradigm you researched to read the full deep reports. \
Extract the `## References` section and the `## Primary Locus` section from each one.
6. Write your final summary including a `## Cross-paradigm interaction map` and a \
consolidated `## References` section at the end (see Output format below).

## Constraints

- Maximum 3 web searches total.
- Only cite authors/papers found in results. Never fabricate.
- After launching all deep research, STOP. Do not search again.
- Discard paradigms that are purely philosophical or lack quantifiable variables.

## Output format (follow exactly)

# Decision-making paradigms: {problem}

## 1. {Paradigm name}
{One-line description}
**Key authors**: {from search results}
**Key concepts**: {list}

## 2. {Paradigm name}
...

## Cross-paradigm interaction map

{Build a matrix table from the `## Primary Locus` sections of all deep reports. \
Collect every distinct brain region / neural substrate mentioned across ALL paradigms \
and use them as columns. Each row is a paradigm. Mark ✓ if the region is relevant \
to that paradigm (mentioned in its Primary Locus), ✗ otherwise.}

| Paradigm | {Region 1} | {Region 2} | {Region 3} | ... |
|----------|:---:|:---:|:---:|:---:|
| {Paradigm 1} | ✓ | ✗ | ✓ | ... |
| {Paradigm 2} | ✗ | ✓ | ✗ | ... |

## References
{Consolidated list of ALL papers cited across ALL deep reports, deduplicated. \
If the same paper appears in multiple deep reports, list it only once. Format each entry as:}
- {Author (Year)} - {Title} — DOI: {doi}
{Omit the DOI part if not available. Sort alphabetically by first author surname.}
"""

_MAX_ITERATIONS = 10


class Researcher:
    def __init__(self, *, client, search: WebSearchPort, reports_dir: Path | None = None):
        self.client = client
        self.search = search
        self.reports_dir = reports_dir

        self._deep_reports: dict[str, str] = {}

        self.tools = [WEB_SEARCH_SCHEMA, LAUNCH_DEEP_RESEARCH_SCHEMA]
        self.registry = {
            "web_search": create_web_search(search),
            "launch_deep_research": create_launch_deep_research(self._run_deep_research),
        }

        if reports_dir:
            self.tools.append(READ_REPORT_SCHEMA)
            self.registry["read_report"] = create_read_report(reports_dir)

    async def _run_deep_research(self, paradigm: str) -> str:
        logger.info("Launching DeepResearcher for paradigm: %s", paradigm)
        dr = DeepResearcher(client=self.client, search=self.search, reports_dir=self.reports_dir)
        summary = await dr.run(paradigm)
        self._deep_reports[paradigm] = summary
        logger.info("DeepResearcher finished for: %s", paradigm)
        return summary

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

        # Save final summary to disk
        if self.reports_dir:
            save_summary_report(self.reports_dir, summary)

        # TODO: extract one-line description from deep report or summary text
        paradigms = [
            Paradigm(id=slugify(name), name=name, description="")
            for name in self._deep_reports
        ]
        return ResearchReport(
            paradigms=paradigms,
            summary=summary,
            deep_reports=dict(self._deep_reports),
        )

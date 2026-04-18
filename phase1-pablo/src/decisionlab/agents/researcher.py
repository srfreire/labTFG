"""Researcher agent — discovers and investigates decision-making paradigms."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from decisionlab.agents.deep_researcher import DeepResearcher
from decisionlab.config import SETTINGS
from decisionlab.domain.models import Paradigm, ResearchReport
from decisionlab.domain.ports import WebSearchPort
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.agents import (
    LAUNCH_DEEP_RESEARCH_SCHEMA,
    create_launch_deep_research,
)
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

_KNOWLEDGE_PROMPT_SECTION = """

## Knowledge Backbone

You have access to a knowledge backbone from past pipeline runs. Before starting web \
searches, call `retrieve_knowledge` to check if this problem domain has been researched \
before. Avoid redundant searches for paradigms already in the knowledge base. Use \
retrieved knowledge to inform your paradigm identification and cross-paradigm interaction \
analysis.
"""

class Researcher:
    def __init__(
        self,
        *,
        client,
        search: WebSearchPort,
        run_id: str | None = None,
        knowledge_tool_schema: dict[str, Any] | None = None,
        knowledge_tool_handler: Callable[[dict], Awaitable[str]] | None = None,
    ):
        self.client = client
        self.search = search
        self.run_id = run_id

        self._deep_reports: dict[str, str] = {}

        self.tools: list[dict[str, Any]] = [
            WEB_SEARCH_SCHEMA,
            LAUNCH_DEEP_RESEARCH_SCHEMA,
        ]
        self.registry: dict[str, Callable[[dict], Awaitable[str]]] = {
            "web_search": create_web_search(search),
            "launch_deep_research": create_launch_deep_research(
                self._run_deep_research
            ),
        }

        if run_id:
            self.tools.append(READ_REPORT_SCHEMA)
            self.registry["read_report"] = create_read_report(run_id)

        self._has_knowledge = False
        if knowledge_tool_schema is not None and knowledge_tool_handler is not None:
            self.tools.append(knowledge_tool_schema)
            self.registry["retrieve_knowledge"] = knowledge_tool_handler
            self._has_knowledge = True

    async def _run_deep_research(self, paradigm: str) -> str:
        logger.info("Launching DeepResearcher for paradigm: %s", paradigm)
        dr = DeepResearcher(client=self.client, search=self.search, run_id=self.run_id)
        summary = await dr.run(paradigm)
        self._deep_reports[paradigm] = summary
        logger.info("DeepResearcher finished for: %s", paradigm)
        return summary

    async def run(self, problem: str) -> ResearchReport:
        self._deep_reports.clear()
        logger.info("Researcher starting — problem: %s", problem)

        messages = [{"role": "user", "content": problem}]

        system = RESEARCHER_SYSTEM_PROMPT
        if self._has_knowledge:
            system += _KNOWLEDGE_PROMPT_SECTION

        cfg = SETTINGS.researcher
        response = await run_agent_loop(
            client=self.client,
            model=cfg.model,
            system=system,
            tools=self.tools,
            messages=messages,
            registry=self.registry,
            max_iterations=cfg.max_iterations,
            max_tokens=cfg.max_tokens,
        )

        summary = "\n".join(b.text for b in response.content if b.type == "text")
        if not summary.strip():
            logger.warning("Researcher produced empty summary for problem: %s", problem)

        # Save final summary to S3
        if self.run_id:
            await save_summary_report(self.run_id, summary)

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

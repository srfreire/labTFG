"""DeepResearcher agent — deep-dives into a single paradigm."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from decisionlab.config import SETTINGS
from decisionlab.domain.ports import WebSearchPort
from decisionlab.runtime import agrex_context
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.runtime.usage import record as record_usage
from decisionlab.tools.papers import SEARCH_PAPERS_SCHEMA, create_search_papers
from decisionlab.tools.reports import save_deep_report, slugify
from decisionlab.tools.search import WEB_SEARCH_SCHEMA, create_web_search

if TYPE_CHECKING:
    from shared.database import DatabaseService
    from shared.storage import StorageService

logger = logging.getLogger(__name__)

DEEP_RESEARCHER_SYSTEM_PROMPT = """\
You produce a scientific report on a single decision-making paradigm.

This report will be used by a mathematical formalization agent to generate equations and \
decision rules for an autonomous agent in a simulation. Focus on quantifiable mechanisms, \
measurable variables, and causal relationships that can be translated into mathematics.

## Tools

You have two search tools — use BOTH:
- **search_papers**: Search OpenAlex for verified academic papers with DOI, authors, \
citations. Use this FIRST for core references and foundational work.
- **web_search**: Search the web for general context, recent developments, and broader information. \
Use this to fill gaps after academic search.

## Process

1. Run 1-2 search_papers queries: paradigm name, paradigm + key theoretical terms.
2. Run 1-2 web searches to fill gaps: paradigm + key authors, paradigm + review paper.
3. Synthesize findings into the report format below.
4. STOP searching. Write the report.

## Constraints

- Maximum 5 total searches (search_papers + web_search combined).
- Only cite papers/authors found in results. Never fabricate.
- If information is insufficient, state gaps explicitly — do not invent.

## Output format (follow exactly)

# {Paradigm name} — Deep research

## Foundations
{Origin, key researchers, theoretical basis.}

## Postulates
P1. {Falsifiable statement} ({Author, Year})

## Assumptions
- {Each assumption}

## Predictions
- {Observable behaviors predicted by this paradigm}

## Primary Locus
{Brain regions / neural substrates relevant to this paradigm, with citations}

## Key Concepts
- **{Term}**: {brief definition as used in this paradigm's literature}

## Identified variables
| Variable | Role | Type | Range | Behavior |
|----------|------|------|-------|----------|

Type: continuous, discrete, binary. Range: plausible values (e.g., [0, 1], positive reals). \
This information is critical for downstream mathematical formalization.

## References
- {Author (Year)} - {Title}
"""

CONCISE_SUMMARY_PROMPT = """\
Summarize the above report in exactly this format (no extra text):

**Paradigm**: {name}
**Key authors**: {comma-separated}
**Core mechanism**: {one sentence}
**Key variables**: {comma-separated}
"""

_KNOWLEDGE_PROMPT_SECTION = """

## Knowledge Backbone

You have access to a knowledge backbone from past pipeline runs. Before starting your \
research loop, call `retrieve_knowledge` to find existing deep research on this paradigm. \
Build on existing postulates, variables, and references rather than starting from scratch. \
Use retrieved knowledge to identify gaps in existing coverage.
"""


class DeepResearcher:
    def __init__(
        self,
        *,
        client,
        search: WebSearchPort,
        storage: StorageService | None = None,
        db: DatabaseService | None = None,
        run_id: str | None = None,
        knowledge_tool_schema: dict[str, Any] | None = None,
        knowledge_tool_handler: Callable[[dict], Awaitable[str]] | None = None,
        paper_search: Callable[[dict], Awaitable[str]] | None = None,
    ):
        self.client = client
        self.run_id = run_id
        self._storage = storage
        self._db = db
        self.tools: list[dict[str, Any]] = [WEB_SEARCH_SCHEMA, SEARCH_PAPERS_SCHEMA]
        self.registry: dict[str, Callable[[dict], Awaitable[str]]] = {
            "web_search": create_web_search(search),
            "search_papers": paper_search or create_search_papers(),
        }

        self._has_knowledge = False
        if knowledge_tool_schema is not None and knowledge_tool_handler is not None:
            self.tools.append(knowledge_tool_schema)
            self.registry["retrieve_knowledge"] = knowledge_tool_handler
            self._has_knowledge = True

    async def run(self, paradigm: str) -> str:
        logger.info("DeepResearcher starting — paradigm: %s", paradigm)
        parent_token = agrex_context.set_parent(
            agrex_context.trace_id("deep_researcher", slugify(paradigm))
        )
        try:
            return await self._run_with_trace_parent(paradigm)
        finally:
            agrex_context.reset_parent(parent_token)

    async def _run_with_trace_parent(self, paradigm: str) -> str:
        messages = [
            {"role": "user", "content": f"Research this paradigm in depth: {paradigm}"}
        ]

        system = DEEP_RESEARCHER_SYSTEM_PROMPT
        if self._has_knowledge:
            system += _KNOWLEDGE_PROMPT_SECTION

        cfg = SETTINGS.deep_researcher
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

        text_blocks = [b.text for b in response.content if b.type == "text"]
        full_report = "\n".join(text_blocks)
        if not full_report.strip():
            logger.warning(
                "DeepResearcher produced empty output for paradigm: %s", paradigm
            )
            return f"No results found for paradigm: {paradigm}"

        if self.run_id and self._storage is not None and self._db is not None:
            await save_deep_report(
                self.run_id,
                paradigm,
                full_report,
                storage=self._storage,
                db=self._db,
            )

        try:
            summary_cfg = SETTINGS.deep_researcher_summary
            summary_response = await self.client.messages.create(
                model=summary_cfg.model,
                system="You summarize research reports concisely. Return ONLY the requested format.",
                messages=[
                    {
                        "role": "user",
                        "content": full_report + "\n\n" + CONCISE_SUMMARY_PROMPT,
                    }
                ],
                max_tokens=summary_cfg.max_tokens,
            )
            record_usage(summary_cfg.model, getattr(summary_response, "usage", None))
            summary = "\n".join(
                b.text for b in summary_response.content if b.type == "text"
            )
        except Exception:
            logger.warning(
                "Summary extraction failed for '%s'; using truncated report",
                paradigm,
                exc_info=True,
            )
            summary = ""

        if not summary.strip():
            summary = full_report[:500] + "\n\n[Full report saved to S3]"

        logger.info(
            "DeepResearcher finished for: %s (report: %d chars, summary: %d chars)",
            paradigm,
            len(full_report),
            len(summary),
        )
        return summary

"""DeepResearcher agent — deep-dives into a single paradigm."""

from __future__ import annotations

import logging
from pathlib import Path

from decisionlab.domain.ports import WebSearchPort
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.reports import save_deep_report
from decisionlab.tools.search import WEB_SEARCH_SCHEMA, create_web_search

logger = logging.getLogger(__name__)

DEEP_RESEARCHER_SYSTEM_PROMPT = """\
You produce a scientific report on a single decision-making paradigm.

## Process

1. Run 2-3 targeted web searches: paradigm + key authors, paradigm + mathematical formulation, paradigm + review paper.
2. Synthesize findings into the report format below.
3. STOP searching. Write the report.

## Constraints

- Maximum 3 web searches.
- Only cite papers/authors found in results. Never fabricate.
- If information is insufficient, state gaps explicitly — do not invent.
- Your FIRST output token MUST be `#`. Never output preamble, commentary, or thinking before the report.

## Output format (follow exactly)

# {Paradigm name} — Deep research

## Foundations
{Origin, key researchers, theoretical basis.}

## Postulates
P1. {Falsifiable statement} ({Author, Year})

## Assumptions
- {Each assumption}

## Predictions
- {Observable behaviors predicted}

## Identified variables
| Variable | Role | Behavior |
|----------|------|----------|

## Mathematical formulation (if applicable)
{Equations, ODEs, update rules from the literature}

## References
- {Author (Year)} - {Title}
"""

CONCISE_SUMMARY_PROMPT = """\
Summarize the above report in exactly this format (no extra text):

**Paradigm**: {name}
**Key authors**: {comma-separated}
**Core mechanism**: {one sentence}
**Key variables**: {comma-separated}
**Mathematical basis**: {yes/no + one-line description if yes}
"""

_MAX_ITERATIONS = 5
_MAX_TOKENS = 16384


class DeepResearcher:
    def __init__(self, *, client, search: WebSearchPort, reports_dir: Path | None = None):
        self.client = client
        self.reports_dir = reports_dir
        self.tools = [WEB_SEARCH_SCHEMA]
        self.registry = {
            "web_search": create_web_search(search),
        }

    async def run(self, paradigm: str) -> str:
        logger.info("DeepResearcher starting — paradigm: %s", paradigm)
        messages = [{"role": "user", "content": f"Research this paradigm in depth: {paradigm}"}]

        response = await run_agent_loop(
            client=self.client,
            model="claude-sonnet-4-6",
            system=DEEP_RESEARCHER_SYSTEM_PROMPT,
            tools=self.tools,
            messages=messages,
            registry=self.registry,
            max_iterations=_MAX_ITERATIONS,
            max_tokens=_MAX_TOKENS,
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        full_report = "\n".join(text_blocks)
        if not full_report.strip():
            logger.warning("DeepResearcher produced empty output for paradigm: %s", paradigm)
            return f"No results found for paradigm: {paradigm}"

        if self.reports_dir:
            save_deep_report(self.reports_dir, paradigm, full_report)

        try:
            summary_response = await self.client.messages.create(
                model="claude-haiku-4-5",
                system="You summarize research reports concisely. Return ONLY the requested format.",
                messages=[{"role": "user", "content": full_report + "\n\n" + CONCISE_SUMMARY_PROMPT}],
                max_tokens=300,
            )
            summary = "\n".join(b.text for b in summary_response.content if b.type == "text")
        except Exception:
            logger.warning("Summary extraction failed for '%s'; using truncated report", paradigm, exc_info=True)
            summary = ""

        if not summary.strip():
            summary = full_report[:500] + "\n\n[Full report saved to disk]"

        logger.info(
            "DeepResearcher finished for: %s (report: %d chars, summary: %d chars)",
            paradigm, len(full_report), len(summary),
        )
        return summary

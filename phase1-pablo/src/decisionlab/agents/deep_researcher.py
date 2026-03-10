from __future__ import annotations

import logging

from decisionlab.domain.ports import PaperSearchPort, WebSearchPort

logger = logging.getLogger(__name__)
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.search import (
    FETCH_PAPER_SCHEMA,
    SEARCH_PAPERS_SCHEMA,
    WEB_SEARCH_SCHEMA,
    create_fetch_paper,
    create_search_papers,
    create_web_search,
)

DEEP_RESEARCHER_SYSTEM_PROMPT = """\
You are a deep research specialist. Your job: given a single decision-making paradigm, produce a thorough scientific report by searching for papers, reading abstracts, and synthesizing findings.

## Process

1. SEARCH for papers and content specific to this paradigm. Use multiple queries: the paradigm name, key authors, key mechanisms, mathematical formulations.

2. FETCH key papers to read their abstracts and metadata. Prioritize foundational papers and recent reviews.

3. SYNTHESIZE findings into a structured report.

## Rules

- DEPTH over breadth. Exhaust this paradigm before finishing.
- Every claim must trace to a specific paper or source from your searches.
- Never fabricate references — only cite papers you found via search tools.
- If you cannot find enough information, say so explicitly rather than inventing content.

## Output format

# {Paradigm name} — Deep research

## Foundations
{What is this paradigm? Origin, key researchers, theoretical basis.}

## Postulates
P1. {Specific, falsifiable statement} ({Author, Year})
P2. ...

## Assumptions
- {Each assumption the model makes}

## Predictions
- {Observable behaviors the model predicts}

## Identified variables
| Variable | Role | Behavior |
|----------|------|----------|
| ... | ... | ... |

## Mathematical formulation (if applicable)
{Equations, ODEs, update rules — as described in the literature}

## References
- {Author (Year)} - {Title} - DOI: {if found}
"""


class DeepResearcher:
    def __init__(self, *, client, search: WebSearchPort, papers: PaperSearchPort):
        self.client = client
        self.tools = [WEB_SEARCH_SCHEMA, SEARCH_PAPERS_SCHEMA, FETCH_PAPER_SCHEMA]
        self.registry = {
            "web_search": create_web_search(search),
            "search_papers": create_search_papers(papers),
            "fetch_paper": create_fetch_paper(papers),
        }

    async def run(self, paradigm: str) -> str:
        messages = [{"role": "user", "content": f"Research this paradigm in depth: {paradigm}"}]

        response = await run_agent_loop(
            client=self.client,
            model="claude-sonnet-4-6",
            system=DEEP_RESEARCHER_SYSTEM_PROMPT,
            tools=self.tools,
            messages=messages,
            registry=self.registry,
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        result = "\n".join(text_blocks)
        if not result.strip():
            logger.warning("DeepResearcher produced empty output for paradigm: %s", paradigm)
        return result

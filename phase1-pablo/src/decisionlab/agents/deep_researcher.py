"""DeepResearcher agent — deep-dives into a single paradigm."""

from __future__ import annotations

import logging

from decisionlab.domain.ports import WebSearchPort
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.search import WEB_SEARCH_SCHEMA, create_web_search

logger = logging.getLogger(__name__)

DEEP_RESEARCHER_SYSTEM_PROMPT = """\
You produce a scientific report on a single decision-making paradigm. You MUST be efficient.

## Process

1. Run 2-3 targeted web searches: paradigm name + key authors, paradigm + mathematical formulation, paradigm + review paper.
2. Synthesize findings into the report format below.
3. STOP. Do not search more than 3 times.

## Constraints

- Maximum 3 web searches. Extract maximum value from each.
- Only cite papers/authors found in results. Never fabricate.
- If information is insufficient, state gaps explicitly — do not invent content.

## Output format

# {Paradigm name} — Deep research

## Foundations
{Origin, key researchers, theoretical basis.}

## Postulates
P1. {Falsifiable statement} ({Author, Year})
P2. ...

## Assumptions
- {Each assumption}

## Predictions
- {Observable behaviors predicted}

## Identified variables
| Variable | Role | Behavior |
|----------|------|----------|
| ... | ... | ... |

## Mathematical formulation (if applicable)
{Equations, ODEs, update rules from the literature}

## References
- {Author (Year)} - {Title}
"""

_MAX_ITERATIONS = 5


class DeepResearcher:
    def __init__(self, *, client, search: WebSearchPort):
        self.client = client
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
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        result = "\n".join(text_blocks)
        if not result.strip():
            logger.warning("DeepResearcher produced empty output for paradigm: %s", paradigm)
        return result

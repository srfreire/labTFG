"""FormalizerSubAgent — reads a deep report and generates mathematical formulations."""

from __future__ import annotations

import logging
from pathlib import Path

from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.files import (
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    create_read_file,
    create_write_file,
)

logger = logging.getLogger(__name__)

FORMALIZER_SUB_SYSTEM_PROMPT = """\
# Mathematical Formulation Agent

You generate 2-3 meaningfully distinct mathematical formulations for a decision-making paradigm,
based on a deep research report.

## Process

1. Read the deep report via `read_file` at `deep/{slug}.md`.
2. Generate 2-3 mathematical formulations that are meaningfully distinct from each other.
3. Each formulation must be self-contained and independently viable.
4. Write the output via `write_file` to `formulations/{slug}.md`.

## Constraints

- Never fabricate references. Only cite authors/papers found in the deep report.
- Each formulation must offer a genuinely different modelling approach.
- Your FIRST output token MUST be `#`. Never output preamble, commentary, or thinking before the report.

## Output format (follow exactly)

# {Paradigm name} — Mathematical formulations

## Formulation 1: {descriptive name}
**Approach**: {one-line description}
**Based on**: {Author (Year) or "derived from postulates P1, P3"}

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|

### Equations
$$
{LaTeX equations}
$$

### Decision logic
{How the agent decides based on this formulation}

## Formulation 2: {descriptive name}
...
"""

_MAX_ITERATIONS = 5
_MAX_TOKENS = 16384


class FormalizerSubAgent:
    def __init__(self, *, client, reports_dir: Path):
        self.client = client
        self.reports_dir = reports_dir
        self.tools = [READ_FILE_SCHEMA, WRITE_FILE_SCHEMA]
        self.registry = {
            "read_file": create_read_file(reports_dir),
            "write_file": create_write_file(reports_dir),
        }

    async def run(self, paradigm_slug: str) -> str:
        logger.info("FormalizerSubAgent starting — paradigm: %s", paradigm_slug)
        messages = [
            {
                "role": "user",
                "content": (
                    f"Formalize this paradigm: {paradigm_slug}\n"
                    f"The deep report is at: deep/{paradigm_slug}.md"
                ),
            }
        ]

        response = await run_agent_loop(
            client=self.client,
            model="claude-opus-4-6",
            system=FORMALIZER_SUB_SYSTEM_PROMPT,
            tools=self.tools,
            messages=messages,
            registry=self.registry,
            max_iterations=_MAX_ITERATIONS,
            max_tokens=_MAX_TOKENS,
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        content = "\n".join(text_blocks)

        logger.info(
            "FormalizerSubAgent finished for: %s (%d chars)",
            paradigm_slug,
            len(content),
        )
        return content

"""FormalizerSubAgent — reads a deep report and generates mathematical formulations."""

from __future__ import annotations

import logging

from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.files import (
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    create_read_file,
    create_write_file,
)

logger = logging.getLogger(__name__)

FORMALIZER_SUB_SYSTEM_PROMPT = """\
You produce 2-3 mathematical formulations for a decision-making paradigm.

Each formulation will later be implemented as an autonomous agent (Python class with \
`decide(perception) -> Action` and `update(action, reward, new_perception)`) that lives \
inside a grid-based simulation. The agent perceives its position, nearby resources, and \
whether it ate, then chooses an action (move up/down/left/right, stay, eat). \
Keep this downstream use in mind: every formulation must be *implementable* as such an agent.

## Process

1. Call `read_file` with path `deep/{slug}.md` to read the deep research report.
2. Analyze the postulates, assumptions, identified variables, and any existing \
mathematical formulations in the report.
3. Design 2-3 formulations that differ in a meaningful way: different equation types \
(ODE vs algebraic vs probabilistic), different variable relationships, or different \
mathematical frameworks. Superficial variations (same equations, different parameter names) \
do NOT count.
4. Call `write_file` with path `formulations/{slug}.md` and the complete output.

## Constraints

- Ground every formulation in the literature cited in the deep report. Never fabricate references.
- Each formulation must be self-contained: a reader should understand it without the others.
- Provide realistic default values for parameters, citing sources when possible.
- Decision logic must specify concrete action-selection rules an agent can execute \
(not vague descriptions like "the agent decides optimally").

## Output format (write this to file, follow exactly)

# {Paradigm name} — Mathematical formulations

## Formulation 1: {descriptive name}
**Approach**: {one-line description of the mathematical framework}
**Based on**: {Author (Year) or "derived from postulates P1, P3"}

### Variables
| Symbol | Name | Description | Type |
|--------|------|-------------|------|

### Parameters
| Symbol | Name | Default | Source |
|--------|------|---------|--------|

### Equations
Write each equation as a labeled pair: plain-text code line + LaTeX block.

Example:

**Eq. 1 — Drive update:**
`dh/dt = c_F · intake − α_F · F`
$$\\frac{dh}{dt} = c_F \\cdot \\text{intake} - \\alpha_F \\cdot F \\tag{1}$$

**Eq. 2 — Action probability:**
`P(a) = exp(β · Q(a)) / Σ_j exp(β · Q(j))`
$$P(a) = \\frac{\\exp(\\beta \\, Q(a))}{\\sum_j \\exp(\\beta \\, Q(j))} \\tag{2}$$

### Decision logic
{Step-by-step rules: given internal state + perception, which action does the agent pick? \
Use pseudocode or numbered if/then rules. Must reference the equations above.}

## Formulation 2: {descriptive name}
...

## Cross-formulation comparison

After ALL formulations, add this comparison table. Each column is one formulation. \
The comparison must reflect real, substantive differences — not superficial rephrasing.

| Aspect | Formulation 1: {name} | Formulation 2: {name} | Formulation 3: {name} |
|--------|----------------------|----------------------|----------------------|
| Framework | {e.g., ODE / Algebraic / Probabilistic} | ... | ... |
| Key variables | {list the 2-3 most important} | ... | ... |
| Core equation | {the single most defining equation} | ... | ... |
| Decision mechanism | {how the agent selects an action} | ... | ... |
| Strengths | {brief, 1-2 points} | ... | ... |
| Limitations | {brief, 1-2 points} | ... | ... |

If only 2 formulations, drop the third column.
"""

_MAX_ITERATIONS = 5
_MAX_TOKENS = 16384


class FormalizerSubAgent:
    def __init__(self, *, client, research_prefix: str, run_id: str | None = None):
        self.client = client
        self.tools = [READ_FILE_SCHEMA, WRITE_FILE_SCHEMA]
        self.registry = {
            "read_file": create_read_file(research_prefix),
            "write_file": create_write_file(research_prefix, run_id=run_id),
        }

    async def run(self, paradigm_slug: str) -> str:
        logger.info("FormalizerSubAgent starting — paradigm: %s", paradigm_slug)
        messages = [
            {
                "role": "user",
                "content": (
                    f"Produce mathematical formulations for the paradigm: {paradigm_slug}\n"
                    f"Read the deep report at: deep/{paradigm_slug}.md"
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

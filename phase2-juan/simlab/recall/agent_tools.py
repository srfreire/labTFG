"""Shared tool injection helpers for Phase 2 agents (P1-003).

Provides ``build_recall_extras`` which returns the tool schema, handler,
and prompt section for a given agent stage.  Each agent calls this once
in its ``run()`` method and extends its own tools/registry/prompt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from simlab.recall.retrieve import RETRIEVE_CONTEXT_TOOL, retrieve_context

if TYPE_CHECKING:
    from shared.services import Services

# ── Per-agent prompt sections ───────────────────────────────────────────

_PROMPT_SECTIONS: dict[str, str] = {
    "architect": """

## Knowledge Backbone access

A "## Knowledge context" section with paradigm facts, previous environment specs, \
and formulations is pre-injected in your input. Use it as your primary reference \
for designing scientifically grounded environments. Call `retrieve_context` with \
a targeted query when the pre-fetch leaves a gap, e.g.:

- A postulate is named in the context but its definition is missing → \
  `retrieve_context(query="definition of <postulate name>", namespace="paradigm")`.
- The paradigm cites a related one you need to compare against → \
  `retrieve_context(query="key properties of <related paradigm>", namespace="paradigm")`.
- You need a concrete environment parameter (grid size, action set) used in a \
  prior simulation → `retrieve_context(query="environment parameters for <paradigm>", namespace="simulation")`.
""",
    "analyst": """

## Postulate cross-check

A "## Knowledge context" section with postulates, formulations, and historical \
data is pre-injected in your input. Use it as your primary reference for \
cross-checking. Call `retrieve_context` with a targeted query when the \
observed data raises a question the pre-fetch doesn't answer, e.g.:

- A behavior pattern in the trajectory isn't explained by the listed postulates → \
  `retrieve_context(query="paradigms predicting <observed pattern>", namespace="paradigm")`.
- You want to compare against a specific past experiment → \
  `retrieve_context(query="simulation outcomes for <paradigm> with <condition>", namespace="simulation")`.
- A formulation in the context has parameters whose meaning is unclear → \
  `retrieve_context(query="parameter <name> in <formulation>", namespace="formulation")`.
""",
    "reporter": """

## References grounding

A "## Knowledge context" section with paper references and formulations is \
pre-injected in your input. Use it for citations and equations. Call \
`retrieve_context` with a targeted query when you need material the pre-fetch \
didn't surface, e.g.:

- You need the original paper for a specific equation → \
  `retrieve_context(query="original publication of <equation name>", namespace="meta")`.
- You want to cite a related paradigm in the discussion → \
  `retrieve_context(query="seminal references for <related paradigm>", namespace="meta")`.
- A formulation needs its full symbolic form, not just a name → \
  `retrieve_context(query="full equation for <formulation>", namespace="formulation")`.
""",
}


# ── Public API ──────────────────────────────────────────────────────────


def build_recall_extras(
    stage: str,
    services: Services,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """Return ``(extra_tools, extra_registry, prompt_section)`` for *stage*.

    *stage* is one of ``"architect"``, ``"analyst"``, ``"reporter"``.
    The caller appends ``extra_tools`` to its tool list, updates its
    registry with ``extra_registry``, and appends ``prompt_section``
    to its system prompt.
    """
    full_stage = f"phase2-{stage}"

    async def _handler(params: dict) -> str:
        query = params.get("query")
        if not query:
            return "## Retrieved Knowledge (0 results)\n\nNo query provided."
        return await retrieve_context(
            services=services,
            query=query,
            namespace=params.get("namespace"),
            top_k=params.get("top_k", 5),
            stage=full_stage,
        )

    return (
        [RETRIEVE_CONTEXT_TOOL],
        {"retrieve_context": _handler},
        _PROMPT_SECTIONS.get(stage, ""),
    )

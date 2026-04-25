"""Shared tool injection helpers for Phase 2 agents (P1-003).

Provides ``build_recall_extras`` which returns the tool schema, handler,
and prompt section for a given agent stage.  Each agent calls this once
in its ``run()`` method and extends its own tools/registry/prompt.
"""

from __future__ import annotations

from typing import Any

from simlab.recall.retrieve import RETRIEVE_CONTEXT_TOOL, retrieve_context

# ── Per-agent prompt sections ───────────────────────────────────────────

_PROMPT_SECTIONS: dict[str, str] = {
    "architect": """

## Knowledge Backbone access

If the user describes a scientific paradigm (e.g. "homeostatic regulation", \
"hedonic control", "reinforcement learning with drive reduction"), call \
`retrieve_context(query="<paradigm name + key concepts>", namespace="paradigm")` \
BEFORE generating the spec. Use the returned facts (variables, postulates, \
observed ranges) to propose an environment that is scientifically grounded.
""",
    "analyst": """

## Postulate cross-check

After identifying behavioural patterns, call \
`retrieve_context(query="postulates for paradigm <name>", namespace="paradigm")` \
and verify whether observations match known postulates. Cite the Postulate \
ID (P1, P2, ...) when reporting a match or mismatch.
""",
    "reporter": """

## References grounding

Before writing the "References" LaTeX section, call \
`retrieve_context(query="papers and authors for paradigm <name>", top_k=10)` \
and use the returned Paper nodes (title, year, DOI, citation_count) to build \
real citations. Fall back to generic references only if the retrieval returns \
zero results.
""",
}


# ── Public API ──────────────────────────────────────────────────────────


def build_recall_extras(
    stage: str,
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

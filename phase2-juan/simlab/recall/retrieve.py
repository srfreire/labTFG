"""Thin wrapper over Pablo's retrieve_knowledge for Phase 2 agents (P1-001).

Exposes ``retrieve_context`` — a single async function that queries the
Knowledge Backbone and returns a markdown-formatted string.  When the
infrastructure is unavailable or ``ENABLE_KNOWLEDGE_READ`` is off, the
function returns a "0 results" stub without touching any external service.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

import shared
from shared.settings import Settings, load_settings

logger = logging.getLogger(__name__)

_EMPTY_RESULT = "## Retrieved Knowledge (0 results)\n\nNo results found."

# ── Anthropic tool schema (R3) ──────────────────────────────────────────

RETRIEVE_CONTEXT_TOOL: dict[str, Any] = {
    "name": "retrieve_context",
    "description": (
        "Query the Knowledge Backbone for scientific facts, papers, postulates, "
        "and patterns from past pipeline runs. Use before generating specs "
        "(Architect), comparing against postulates (Analyst), or citing "
        "references (Reporter)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language query"},
            "namespace": {
                "type": "string",
                "enum": ["paradigm", "formulation", "model", "simulation", "meta"],
                "description": "Optional namespace filter",
            },
            "top_k": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
}

# ── Core wrapper ────────────────────────────────────────────────────────


async def retrieve_context(
    *,
    query: str,
    namespace: str | None = None,
    top_k: int = 5,
    as_of: str | None = None,
    stage: str = "phase2",
    run_id: str | None = None,
) -> str:
    """Retrieve relevant knowledge from the backbone.

    Returns a markdown-formatted string.  Never raises — any failure is
    logged and the caller receives *_EMPTY_RESULT*.
    """
    settings = load_settings()
    if not settings.ENABLE_KNOWLEDGE_READ:
        return _EMPTY_RESULT

    if shared.vectors is None and shared.embeddings is None and shared.kg is None:
        logger.debug("Knowledge infra unavailable — returning empty result")
        return _EMPTY_RESULT

    try:
        from anthropic import AsyncAnthropic

        from decisionlab.knowledge.retrieval.tool import create_retrieve_knowledge

        client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env
        handler = create_retrieve_knowledge(
            kg=shared.kg,
            vector_store=shared.vectors,
            embedding_service=shared.embeddings,
            search_adapter=None,
            client=client,
            run_id=run_id or str(uuid.uuid4()),
            stage=stage,
        )
        params: dict[str, Any] = {"query": query, "top_k": top_k}
        if namespace is not None:
            params["namespace"] = namespace
        if as_of is not None:
            params["as_of"] = as_of
        return await handler(params)
    except Exception:
        logger.exception("retrieve_context failed — returning empty result")
        return _EMPTY_RESULT


# ── Factory ─────────────────────────────────────────────────────────────


async def build_retriever_from_settings(
    settings: Settings | None = None,
) -> Callable[..., Any] | None:
    """Return a ready-to-call retriever, or *None* if the feature is off.

    Useful for tests and for Phase 2 integration code that wants to
    pre-check availability before wiring the tool into an agent.
    """
    if settings is None:
        settings = load_settings()

    if not settings.ENABLE_KNOWLEDGE_READ:
        return None

    if shared.vectors is None and shared.embeddings is None and shared.kg is None:
        logger.warning("ENABLE_KNOWLEDGE_READ=true but knowledge infra unavailable")
        return None

    return retrieve_context

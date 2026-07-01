"""Thin wrapper over Pablo's retrieve_knowledge for Phase 2 agents (P1-001).

Exposes ``retrieve_context`` — a single async function that queries the
Knowledge Backbone and returns a markdown-formatted string.  When the
infrastructure is unavailable or ``ENABLE_KNOWLEDGE_READ`` is off, the
function returns a "0 results" stub without touching any external service.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from shared.settings import Settings, load_settings

if TYPE_CHECKING:
    from shared.services import Services

logger = logging.getLogger(__name__)

_EMPTY_RESULT = "## Retrieved Knowledge (0 results)\n\nNo results found."
_RETRIEVE_CONTEXT_TIMEOUT_SECONDS = 20

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


async def retrieve_context(
    *,
    services: Services,
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

    Callers must pass an explicit ``Services`` (constructed via
    ``init_services``). The ENABLE_KNOWLEDGE_READ flag still gates the
    call: with the flag off this returns ``_EMPTY_RESULT`` immediately
    without touching ``services``.
    """
    settings = load_settings()
    if not settings.ENABLE_KNOWLEDGE_READ:
        return _EMPTY_RESULT

    if services is None:
        return _EMPTY_RESULT

    if services.vectors is None and services.embeddings is None and services.kg is None:
        logger.debug("Knowledge infra unavailable — returning empty result")
        return _EMPTY_RESULT

    try:
        from anthropic import AsyncAnthropic

        from decisionlab.knowledge.retrieval.tool import create_retrieve_knowledge

        client = AsyncAnthropic(timeout=120.0)  # reads ANTHROPIC_API_KEY from env
        handler = create_retrieve_knowledge(
            kg=services.kg,
            vector_store=services.vectors,
            embedding_service=services.embeddings,
            search_adapter=None,
            client=client,
            run_id=run_id or str(uuid.uuid4()),
            stage=stage,
            db=services.db,
        )
        params: dict[str, Any] = {"query": query, "top_k": top_k}
        if namespace is not None:
            params["namespace"] = namespace
        if as_of is not None:
            params["as_of"] = as_of
        return await asyncio.wait_for(
            handler(params), timeout=_RETRIEVE_CONTEXT_TIMEOUT_SECONDS
        )
    except TimeoutError:
        logger.warning(
            "retrieve_context timed out after %ss — returning empty result",
            _RETRIEVE_CONTEXT_TIMEOUT_SECONDS,
        )
        return _EMPTY_RESULT
    except Exception:
        logger.exception("retrieve_context failed — returning empty result")
        return _EMPTY_RESULT


async def build_retriever_from_settings(
    services: Services,
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

    if services is None:
        return None
    if services.vectors is None and services.embeddings is None and services.kg is None:
        logger.warning("ENABLE_KNOWLEDGE_READ=true but knowledge infra unavailable")
        return None

    async def _bound(
        *,
        query: str,
        namespace: str | None = None,
        top_k: int = 5,
        as_of: str | None = None,
        stage: str = "phase2",
        run_id: str | None = None,
    ) -> str:
        return await retrieve_context(
            services=services,
            query=query,
            namespace=namespace,
            top_k=top_k,
            as_of=as_of,
            stage=stage,
            run_id=run_id,
        )

    return _bound

"""Unified retrieve_knowledge tool for pipeline agents (P3-005).

Exposes the full 3-layer retrieval + CRAG pipeline as a single tool function
that any pipeline agent can call. Follows the existing tool factory pattern.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import shared
from shared.embedding import EmbeddingService
from shared.knowledge_graph import KnowledgeGraph
from shared.memories import touch_memory
from shared.vector_store import VectorStore

from anthropic import AsyncAnthropic

from decisionlab.domain.ports import WebSearchPort
from decisionlab.knowledge.retrieval.crag import evaluate_results
from decisionlab.knowledge.retrieval.fusion import fuse_and_rerank
from decisionlab.knowledge.retrieval.kg_retrieval import kg_retrieve
from decisionlab.knowledge.retrieval.models import RetrievalResult
from decisionlab.knowledge.retrieval.vector_retrieval import vector_retrieve

logger = logging.getLogger(__name__)

# Stage → human-readable description for CRAG task_context
_STAGE_DESCRIPTIONS: dict[str, str] = {
    "researcher": "researching scientific paradigms and gathering literature",
    "formalizer": "writing mathematical formulations for decision-making models",
    "reasoner": "building environment specifications and validation criteria",
    "builder": "generating Python model code and test suites",
    "memory_agent": "curating and consolidating knowledge across pipeline runs",
}

RETRIEVE_KNOWLEDGE_SCHEMA: dict[str, Any] = {
    "name": "retrieve_knowledge",
    "description": (
        "Query the knowledge backbone for relevant research, formulations, "
        "model patterns, and scientific facts from past pipeline runs and the "
        "current knowledge graph. Use this to find existing knowledge before "
        "generating new content."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language query describing what knowledge you need",
            },
            "namespace": {
                "type": "string",
                "enum": ["paradigm", "formulation", "model", "simulation", "meta"],
                "description": "Optional: restrict search to a specific knowledge namespace",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5,
            },
            "as_of": {
                "type": "string",
                "description": (
                    "Optional ISO8601 timestamp. When set, only return knowledge "
                    "that was valid at this point in time (created_at <= as_of "
                    "and not yet expired). Default: current knowledge only."
                ),
            },
        },
        "required": ["query"],
    },
}


def _build_task_context(stage: str) -> str:
    desc = _STAGE_DESCRIPTIONS.get(stage, f"working in the {stage} stage")
    return f"The {stage} agent is {desc}."


def _format_result(idx: int, result: RetrievalResult) -> str:
    meta = result.metadata

    if result.source == "web":
        title = meta.get("title", "Web result")
        url = meta.get("url", "")
        attribution = f"Source: {title}"
        if url:
            attribution += f" | URL: {url}"
        header = f"### Result {idx} [source: web | fresh search]"
    else:
        header = f"### Result {idx} [source: {result.source} | confidence: {result.score:.2f}]"
        parts = []
        if "paper_title" in meta:
            parts.append(f'"{meta["paper_title"]}"')
        if "namespace" in meta:
            parts.append(f"Namespace: {meta['namespace']}")
        if "source_stage" in meta:
            parts.append(f"Stage: {meta['source_stage']}")
        if "run_id" in meta:
            parts.append(f"Run: {meta['run_id']}")
        attribution = "Source: " + " | ".join(parts) if parts else ""

    lines = [header, result.text]
    if attribution:
        lines.append(f"\u2014 {attribution}")
    return "\n".join(lines)


def _format_output(results: list[RetrievalResult], top_k: int) -> str:
    limited = results[:top_k]
    if not limited:
        return "## Retrieved Knowledge (0 results)\n\nNo results found for this query."

    blocks = [f"## Retrieved Knowledge ({len(limited)} results)"]
    for i, r in enumerate(limited, start=1):
        blocks.append("")
        blocks.append(_format_result(i, r))

    return "\n".join(blocks)


async def _track_memory_access(results: list[RetrievalResult]) -> None:
    """Call touch_memory for each Postgres-backed result."""
    if shared.db is None:
        return

    memory_ids: list[uuid.UUID] = []
    for r in results:
        entity_id = r.metadata.get("entity_id")
        collection = r.metadata.get("collection", "")
        if entity_id and "memories" in collection:
            try:
                memory_ids.append(uuid.UUID(entity_id))
            except (ValueError, TypeError):
                continue

    if not memory_ids:
        return

    async with shared.db.get_session() as session:
        for mid in memory_ids:
            try:
                await touch_memory(session, mid)
            except Exception as exc:
                logger.warning("touch_memory failed for %s: %s", mid, exc)
        await session.commit()


_RECENCY_DECAY = 0.995


def _parse_utc(value: object) -> datetime | None:
    """Parse an ISO 8601 string into a timezone-aware UTC datetime.

    Returns None when *value* is falsy or unparseable.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _result_created_at(r: RetrievalResult) -> datetime | None:
    """Extract and parse the creation timestamp from a retrieval result."""
    return _parse_utc(r.metadata.get("created_at") or r.metadata.get("run_date"))


def _apply_recency_weighting(
    results: list[RetrievalResult],
) -> list[RetrievalResult]:
    """Apply recency and confidence-based score weighting.

    For each result:
        recency_factor = 0.995 ** days_old  (1.0 if no timestamp)
        confidence_factor = metadata["confidence"]  (1.0 if missing)
        final_score = score * recency_factor * confidence_factor

    Returns a new list re-sorted by final_score descending.
    """
    now = datetime.now(timezone.utc)
    weighted: list[RetrievalResult] = []

    for r in results:
        created_at = _result_created_at(r)
        recency_factor = 1.0

        if created_at is not None:
            days_old = max(0, (now - created_at).days)
            recency_factor = _RECENCY_DECAY**days_old

        confidence_factor = max(0.0, min(1.0, float(r.metadata.get("confidence", 1.0))))

        final_score = r.score * recency_factor * confidence_factor
        weighted.append(
            RetrievalResult(
                text=r.text,
                score=final_score,
                source=r.source,
                metadata={
                    **r.metadata,
                    "recency_factor": recency_factor,
                    "confidence_factor": confidence_factor,
                },
            )
        )

    weighted.sort(key=lambda r: r.score, reverse=True)
    return weighted


def _apply_temporal_filter(
    results: list[RetrievalResult],
    as_of: datetime | None,
) -> list[RetrievalResult]:
    """Filter results to only those valid at *as_of*.

    When as_of is None, returns all results unchanged (current-knowledge mode).
    When set, keeps results where:
        created_at <= as_of AND (valid_to is absent OR valid_to > as_of)
    Results without a created_at timestamp are excluded when as_of is set.
    """
    if as_of is None:
        return results

    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    filtered: list[RetrievalResult] = []
    for r in results:
        created = _result_created_at(r)
        if created is None or created > as_of:
            continue

        valid_to_raw = r.metadata.get("valid_to")
        if valid_to_raw:
            valid_to = _parse_utc(valid_to_raw)
            if valid_to is None:
                # Present but unparseable — exclude conservatively
                continue
            if valid_to <= as_of:
                continue

        filtered.append(r)

    return filtered


async def _noop_kg() -> list[RetrievalResult]:
    return []


async def _noop_vec() -> tuple[list[RetrievalResult], list[RetrievalResult]]:
    return [], []


def create_retrieve_knowledge(
    kg: KnowledgeGraph | None,
    vector_store: VectorStore | None,
    embedding_service: EmbeddingService | None,
    search_adapter: WebSearchPort | None,
    client: AsyncAnthropic,
    run_id: str,
    stage: str,
) -> Callable[[dict], Awaitable[str]]:
    """Factory that creates the retrieve_knowledge tool handler.

    Captures all dependencies via closure. The returned handler accepts
    a params dict (from the Anthropic API) and returns a formatted string.
    """

    async def handle_retrieve_knowledge(params: dict) -> str:
        if "query" not in params:
            raise ValueError("retrieve_knowledge requires 'query' parameter")

        query = params["query"]
        namespace: str | None = params.get("namespace")
        top_k: int = params.get("top_k", 5)
        as_of = _parse_utc(params.get("as_of"))
        if params.get("as_of") and as_of is None:
            logger.warning("Unparseable as_of value: %r", params["as_of"])

        # Graceful degradation: all infrastructure unavailable
        if kg is None and vector_store is None and embedding_service is None:
            return "Knowledge backbone not available. Proceeding without retrieved context."

        try:
            # Build filters
            filters: dict[str, object] = {"exclude_run_id": run_id}
            if namespace:
                filters["namespace"] = namespace

            # Run retrieval channels in parallel (fallback to empty when infra missing)
            kg_coro = (
                kg_retrieve(query, kg, embedding_service, client)
                if kg is not None and embedding_service is not None
                else _noop_kg()
            )
            vec_coro = (
                vector_retrieve(query, embedding_service, vector_store, filters=filters)
                if vector_store is not None and embedding_service is not None
                else _noop_vec()
            )

            kg_results, (dense_results, sparse_results) = await asyncio.gather(
                kg_coro,
                vec_coro,
            )

            # Fuse + rerank
            if not embedding_service:
                # Without embedding service, just concatenate raw results
                reranked = (kg_results + dense_results + sparse_results)[:top_k]
            else:
                reranked = await fuse_and_rerank(
                    query,
                    kg_results,
                    dense_results,
                    sparse_results,
                    embedding_service,
                )

            # CRAG evaluation
            task_context = _build_task_context(stage)
            crag_result = await evaluate_results(
                query,
                task_context,
                reranked,
                client,
                search_adapter=search_adapter,
                embedding_service=embedding_service,
            )

            # Apply recency weighting (P5-001)
            weighted_results = _apply_recency_weighting(crag_result.results)

            # Apply temporal filter when as_of is specified (P5-004)
            final_results = _apply_temporal_filter(weighted_results, as_of)

            # Track memory access (fire-and-forget, don't block response)
            try:
                await _track_memory_access(final_results)
            except Exception as exc:
                logger.warning("Memory access tracking failed: %s", exc)

            return _format_output(final_results, top_k)

        except Exception as exc:
            logger.error(
                "retrieve_knowledge failed (stage=%s): %s",
                stage,
                exc,
            )
            return (
                "Knowledge backbone temporarily unavailable. "
                "Proceeding without retrieved context."
            )

    return handle_retrieve_knowledge

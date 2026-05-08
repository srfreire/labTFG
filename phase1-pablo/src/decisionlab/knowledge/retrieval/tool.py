"""Unified retrieve_knowledge tool for pipeline agents (P3-005).

Exposes the full 3-layer retrieval + CRAG pipeline as a single tool function
that any pipeline agent can call. Follows the existing tool factory pattern.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from anthropic import AsyncAnthropic

import shared
from decisionlab.config import SETTINGS
from decisionlab.domain.ports import WebSearchPort
from decisionlab.knowledge.retrieval.crag import evaluate_results
from decisionlab.knowledge.retrieval.fusion import fuse_and_rerank
from decisionlab.knowledge.retrieval.kg_retrieval import kg_retrieve
from decisionlab.knowledge.retrieval.models import CRAGResult, RetrievalResult
from decisionlab.knowledge.retrieval.vector_retrieval import vector_retrieve
from decisionlab.runtime.usage import increment_counter
from shared.embedding import EmbeddingService
from shared.knowledge_graph import KnowledgeGraph
from shared.memories import touch_memory
from shared.vector_store import VectorStore

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


def _final_truncate(
    results: list[RetrievalResult],
    *,
    top_k: int,
    web_supplemented: bool,
) -> list[RetrievalResult]:
    """Cap the result list at the agent boundary.

    When CRAG supplemented results from the web, the cap stretches to
    ``2 * top_k`` so the agent sees both the kept stored hits and the
    fresh web ones — clipping back to ``top_k`` would silently discard
    exactly the supplements CRAG asked for.
    """
    cap = top_k * 2 if web_supplemented else top_k
    return results[:cap]


def _format_output(results: list[RetrievalResult], top_k: int) -> str:
    limited = results[:top_k]
    if not limited:
        return "## Retrieved Knowledge (0 results)\n\nNo results found for this query."

    blocks = [f"## Retrieved Knowledge ({len(limited)} results)"]
    for i, r in enumerate(limited, start=1):
        blocks.append("")
        blocks.append(_format_result(i, r))

    return "\n".join(blocks)


def _get_kg() -> KnowledgeGraph | None:
    """Module-level KG accessor — overridable in tests via monkeypatch."""
    return getattr(shared, "kg", None)


def _get_vector_store() -> VectorStore | None:
    return getattr(shared, "vectors", None)


def _get_embedding_service() -> EmbeddingService | None:
    return getattr(shared, "embeddings", None)


async def list_known_slugs(
    query: str,
    *,
    namespace: str = "paradigm",
    top_k: int = 8,
) -> list[tuple[str, str]]:
    """Return ``[(slug, definition), ...]`` for the top-k matching paradigm
    nodes — structured KG output, not parsed markdown.

    Ranking order:
      1. When the vector store + embedding service are wired, run a dense
         retrieval over ``namespace=paradigm`` to score candidate slugs by
         relevance to the query, then hydrate definitions from the KG.
      2. When vector infra is unavailable (degraded mode, tests), fall back
         to a plain ``MATCH (p:Paradigm) ... LIMIT $k`` — order is whatever
         the KG returns, but the helper still produces something rather
         than empty.
      3. KG missing → empty list (preserves the Researcher's "no candidates
         → __NEW__ for everything" fallback).

    Paradigm-only today; other namespaces don't have a comparable slug
    field on their nodes.
    """
    if namespace != "paradigm":
        raise ValueError(
            f"list_known_slugs: unsupported namespace {namespace!r} "
            "(paradigm-only today)"
        )

    kg = _get_kg()
    if kg is None:
        return []

    vector_store = _get_vector_store()
    embedding_service = _get_embedding_service()

    candidate_slugs: list[str] = []
    if vector_store is not None and embedding_service is not None:
        try:
            dense, sparse = await vector_retrieve(
                query=query,
                embedding_service=embedding_service,
                vector_store=vector_store,
                limit=top_k * 2,
                filters={"namespace": "paradigm"},
            )
        except Exception as exc:
            logger.warning("list_known_slugs: vector_retrieve failed: %s", exc)
            dense, sparse = [], []
        seen: set[str] = set()
        for h in sorted(dense + sparse, key=lambda r: r.score, reverse=True):
            slug = h.metadata.get("slug")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            candidate_slugs.append(slug)
            if len(candidate_slugs) >= top_k:
                break

    if not candidate_slugs:
        # Degraded path — return the first top_k Paradigm nodes from the KG
        # in whatever order it gives them.
        rows = await kg.execute_query(
            "MATCH (p:Paradigm) "
            "RETURN p.slug AS slug, p.name AS name, p.description AS description "
            "LIMIT $k",
            {"k": top_k},
        )
        return [(r["slug"], r.get("description") or "") for r in rows]

    rows = await kg.execute_query(
        "MATCH (p:Paradigm) WHERE p.slug IN $slugs "
        "RETURN p.slug AS slug, p.description AS description",
        {"slugs": candidate_slugs},
    )
    desc_by_slug = {r["slug"]: (r.get("description") or "") for r in rows}
    return [(s, desc_by_slug.get(s, "")) for s in candidate_slugs]


async def _track_memory_access(results: list[RetrievalResult]) -> None:
    """Bump access metadata for Postgres-backed results in a single UPDATE."""
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
        try:
            await touch_memory(session, memory_ids)
            await session.commit()
        except Exception as exc:
            logger.warning(
                "touch_memory failed for batch of %d: %s", len(memory_ids), exc
            )
            return

    logger.info("touch_memory.batch_size=%d", len(memory_ids))


# Recency decay rates per namespace, applied as decay**days_old.
# Slower decay for foundational knowledge (paradigm/formulation papers age
# slowly), faster for generated artifacts (code, simulation traces).
# At 100 days: 0.999→90%, 0.998→82%, 0.997→74%, 0.995→61%, 0.99→37%.
_RECENCY_DECAY_BY_NAMESPACE: dict[str, float] = {
    "paradigm": 0.999,
    "formulation": 0.998,
    "meta": 0.997,
    "model": 0.995,
    "simulation": 0.99,
}
_DEFAULT_RECENCY_DECAY = 0.995


def _decay_rate_for(namespace: object) -> float:
    if isinstance(namespace, str):
        return _RECENCY_DECAY_BY_NAMESPACE.get(namespace, _DEFAULT_RECENCY_DECAY)
    return _DEFAULT_RECENCY_DECAY


def _parse_utc(value: object) -> datetime | None:
    """Parse an ISO 8601 string into a timezone-aware UTC datetime.

    Returns None when *value* is falsy or unparseable.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
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
        decay_rate = _RECENCY_DECAY_BY_NAMESPACE[namespace]  (default 0.995)
        recency_factor = decay_rate ** days_old  (1.0 if no timestamp)
        confidence_factor = metadata["confidence"]  (1.0 if missing)
        final_score = score * recency_factor * confidence_factor

    Returns a new list re-sorted by final_score descending.
    """
    now = datetime.now(UTC)
    weighted: list[RetrievalResult] = []

    for r in results:
        created_at = _result_created_at(r)
        recency_factor = 1.0
        decay_rate = _decay_rate_for(r.metadata.get("namespace"))

        if created_at is not None:
            days_old = max(0, (now - created_at).days)
            recency_factor = decay_rate**days_old

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
        as_of = as_of.replace(tzinfo=UTC)

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

            # P2-002 / R2 — sequential by design: dense first, then a
            # conditional kg_retrieve. The previous parallel asyncio.gather
            # was removed deliberately so the dense top-1 score can gate
            # the Haiku NER call inside kg_retrieve. The non-skip path
            # pays vector + kg in series; the skip path saves the kg leg
            # entirely. Don't re-parallelise — the gate would be lost.
            if vector_store is not None and embedding_service is not None:
                dense_results, sparse_results = await vector_retrieve(
                    query, embedding_service, vector_store, filters=filters
                )
            else:
                dense_results, sparse_results = [], []

            kg_available = kg is not None and embedding_service is not None
            dense_top1 = dense_results[0].score if dense_results else 0.0

            if not kg_available:
                kg_results = []
                increment_counter("ner.unavailable")
            elif dense_top1 >= SETTINGS.ner_skip_threshold:
                kg_results = []
                increment_counter("ner.skipped")
            else:
                kg_results = await kg_retrieve(query, kg, embedding_service, client)
                increment_counter("ner.evaluated")

            # Fuse + rerank — keep up to 2*top_k candidates through this
            # stage so CRAG can web-supplement without us pre-clipping
            # the results it would've kept.
            if not embedding_service:
                # Degraded path: no rerank service. Sort by raw channel
                # score so reranked[0] is genuinely the top hit — the
                # CRAG-skip branch below assumes a score-descending order.
                reranked = sorted(
                    kg_results + dense_results + sparse_results,
                    key=lambda r: r.score,
                    reverse=True,
                )[: top_k * 2]
            else:
                reranked = await fuse_and_rerank(
                    query,
                    kg_results,
                    dense_results,
                    sparse_results,
                    embedding_service,
                )

            # Conditional CRAG (P2-001): if the rerank's top hit is
            # already confident, skip the Haiku grader entirely — it's
            # the largest single contributor to retrieve_p95, so this is
            # the cheapest latency win available here.
            top_score = max((r.score for r in reranked[:top_k]), default=0.0)
            if top_score >= SETTINGS.crag_skip_threshold:
                increment_counter("crag.skipped")
                crag_result = CRAGResult(
                    results=reranked[: top_k * 2],
                    action="rerank_pass_through",
                    evaluations=[],
                    web_results_used=0,
                    grading_failed=False,
                )
            else:
                increment_counter("crag.evaluated")
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

            # Truncate at the agent boundary. When CRAG added a web
            # supplement, allow up to 2*top_k so the supplemented hits
            # actually reach the agent.
            final_results = _final_truncate(
                final_results,
                top_k=top_k,
                web_supplemented=crag_result.web_results_used > 0,
            )

            # Track memory access (fire-and-forget, don't block response)
            try:
                await _track_memory_access(final_results)
            except Exception as exc:
                logger.warning("Memory access tracking failed: %s", exc)

            # _format_output's own ``[:top_k]`` is now a defensive no-op
            # because final_results is already capped — pass len() so it
            # does not re-clip the supplemented set.
            return _format_output(final_results, len(final_results) or top_k)

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

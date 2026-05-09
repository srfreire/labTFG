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

from decisionlab.config import SETTINGS
from decisionlab.domain.ports import WebSearchPort
from decisionlab.knowledge.retrieval.crag import evaluate_results
from decisionlab.knowledge.retrieval.fusion import fuse_and_rerank
from decisionlab.knowledge.retrieval.kg_retrieval import kg_retrieve
from decisionlab.knowledge.retrieval.models import CRAGResult, RetrievalResult
from decisionlab.knowledge.retrieval.vector_retrieval import vector_retrieve
from decisionlab.runtime.usage import increment_counter
from shared.database import DatabaseService
from shared.embedding import EmbeddingService
from shared.knowledge_graph import KnowledgeGraph
from shared.pipeline_memories import touch_memory
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


def _format_output(
    results: list[RetrievalResult],
    top_k: int,
    *,
    grader_unavailable: bool = False,
) -> str:
    """Format the agent-facing retrieval response.

    When ``grader_unavailable`` is set the header carries a
    ``[grader_unavailable]`` marker so the agent can attribute the
    bypassed CRAG grade to a degraded Haiku rather than a confident
    rerank pass-through.
    """
    limited = results[:top_k]
    marker = " [grader_unavailable]" if grader_unavailable else ""
    if not limited:
        return (
            f"## Retrieved Knowledge (0 results){marker}"
            "\n\nNo results found for this query."
        )

    blocks = [f"## Retrieved Knowledge ({len(limited)} results){marker}"]
    for i, r in enumerate(limited, start=1):
        blocks.append("")
        blocks.append(_format_result(i, r))

    return "\n".join(blocks)


async def list_known_slugs(
    query: str,
    *,
    kg: KnowledgeGraph | None,
    vectors: VectorStore | None,
    embeddings: EmbeddingService | None,
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

    if kg is None:
        return []

    candidate_slugs: list[str] = []
    if vectors is not None and embeddings is not None:
        try:
            dense, sparse = await vector_retrieve(
                query=query,
                embedding_service=embeddings,
                vector_store=vectors,
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
        rows = await kg.query(
            "MATCH (p:Paradigm) "
            "RETURN p.slug AS slug, p.name AS name, p.description AS description "
            "LIMIT $k",
            {"k": top_k},
        )
        return [(r["slug"], r.get("description") or "") for r in rows]

    rows = await kg.query(
        "MATCH (p:Paradigm) WHERE p.slug IN $slugs "
        "RETURN p.slug AS slug, p.description AS description",
        {"slugs": candidate_slugs},
    )
    desc_by_slug = {r["slug"]: (r.get("description") or "") for r in rows}
    return [(s, desc_by_slug.get(s, "")) for s in candidate_slugs]


def _source_kind_of(metadata: dict) -> str:
    """Return ``"pipeline"`` or ``"simulation"`` for a retrieval result.

    Reads the ``source_kind`` Qdrant payload field added in P4-003. Falls
    back to inferring from ``namespace`` for legacy points written before
    the field landed (anything in namespace ``simulation`` is a Phase 2
    observation; everything else is a Phase 1 pipeline memory).
    """
    raw = metadata.get("source_kind")
    if raw in ("pipeline", "simulation"):
        return raw  # type: ignore[return-value]
    return "simulation" if metadata.get("namespace") == "simulation" else "pipeline"


async def _track_memory_access(
    results: list[RetrievalResult], db: DatabaseService | None
) -> None:
    """Bump access metadata for Phase 1 (``pipeline_memories``) results.

    Phase 2 observations live in ``simulation_observations`` which has no
    ``last_accessed_at`` / ``access_count`` columns — they are write-once
    records, so nothing to touch on read.
    """
    if db is None:
        return

    memory_ids: list[uuid.UUID] = []
    for r in results:
        entity_id = r.metadata.get("entity_id") or r.metadata.get("memory_id")
        collection = r.metadata.get("collection", "")
        if not entity_id or "memories" not in collection:
            continue
        if _source_kind_of(r.metadata) != "pipeline":
            continue
        try:
            memory_ids.append(uuid.UUID(entity_id))
        except (ValueError, TypeError):
            continue

    if not memory_ids:
        return

    async with db.get_session() as session:
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


def _collect_memory_ids(results: list[RetrievalResult]) -> list[uuid.UUID]:
    """Pull UUIDs of memory-backed results, skipping malformed ids.

    Phase 1 payloads carry the UUID under ``entity_id``; Phase 2 payloads
    historically used ``memory_id`` (pre-P4-003). Both shapes are accepted
    so retrieval keeps reading legacy and new points equally.
    """
    memory_ids: list[uuid.UUID] = []
    for r in results:
        if "memories" not in r.metadata.get("collection", ""):
            continue
        entity_id = r.metadata.get("entity_id") or r.metadata.get("memory_id")
        if not entity_id:
            continue
        try:
            memory_ids.append(uuid.UUID(str(entity_id)))
        except (ValueError, TypeError):
            continue
    return memory_ids


async def _fetch_confidences(
    memory_ids: list[uuid.UUID], db: DatabaseService | None
) -> dict[uuid.UUID, float]:
    """Batched SELECT across both memory tables for live confidences.

    Queries ``pipeline_memories`` and ``simulation_observations`` in a
    single round-trip via ``UNION``; an id is in at most one table by
    construction (UUIDs are unique across both tables since each is
    minted at write time).

    Returns an empty map when there are no memory IDs, when ``db`` is
    unwired, or when the DB raises. Callers fall back to a 1.0 factor
    so a degraded PG never silently kills a retrieve — failures are
    logged at WARNING instead.
    """
    if not memory_ids:
        return {}
    if db is None:
        logger.warning(
            "_fetch_confidences: db is None, scoring %d memories with "
            "confidence_factor=1.0",
            len(memory_ids),
        )
        return {}

    from sqlalchemy import select, union

    from shared.models import PipelineMemory, SimulationObservation

    # ``union`` (not ``union_all``) — by construction each UUID lives in at
    # most one table, but a stray duplicate from a botched
    # rollback/re-upgrade cycle would otherwise yield two rows and a
    # non-deterministic dict comprehension. Deduplicating server-side is
    # cheap insurance.
    pipeline_q = select(
        PipelineMemory.id.label("id"),
        PipelineMemory.confidence.label("confidence"),
    ).where(PipelineMemory.id.in_(memory_ids))
    sim_q = select(
        SimulationObservation.id.label("id"),
        SimulationObservation.confidence.label("confidence"),
    ).where(SimulationObservation.id.in_(memory_ids))
    stmt = union(pipeline_q, sim_q)

    try:
        async with db.get_session() as session:
            result = await session.execute(stmt)
            return {row.id: row.confidence for row in result.all()}
    except Exception as exc:
        logger.warning(
            "_fetch_confidences: PG fetch failed for %d ids, defaulting to "
            "confidence_factor=1.0: %s",
            len(memory_ids),
            exc,
        )
        return {}


async def _apply_recency_weighting(
    results: list[RetrievalResult],
    db: DatabaseService | None,
) -> list[RetrievalResult]:
    """Apply recency and confidence-based score weighting.

    For each result:
        decay_rate = _RECENCY_DECAY_BY_NAMESPACE[namespace]  (default 0.995)
        recency_factor = decay_rate ** days_old  (1.0 if no timestamp)
        confidence_factor = PG `memories.confidence`  (1.0 if not memory-backed)
        final_score = score * recency_factor * confidence_factor

    P3-002: confidence is read from Postgres in one batched SELECT rather
    than per-result `metadata["confidence"]`. Qdrant payload confidence
    drifted (sparse never synced), so it is no longer trusted; artifact-
    only results without a PG row keep `confidence_factor = 1.0`.

    Returns a new list re-sorted by final_score descending.
    """
    now = datetime.now(UTC)
    conf_map = await _fetch_confidences(_collect_memory_ids(results), db)
    weighted: list[RetrievalResult] = []

    for r in results:
        created_at = _result_created_at(r)
        recency_factor = 1.0
        decay_rate = _decay_rate_for(r.metadata.get("namespace"))

        if created_at is not None:
            days_old = max(0, (now - created_at).days)
            recency_factor = decay_rate**days_old

        confidence_factor = 1.0
        entity_id = r.metadata.get("entity_id") or r.metadata.get("memory_id")
        if entity_id and "memories" in r.metadata.get("collection", ""):
            try:
                pg_confidence = conf_map.get(uuid.UUID(str(entity_id)))
            except (ValueError, TypeError):
                pg_confidence = None
            if pg_confidence is not None:
                confidence_factor = max(0.0, min(1.0, float(pg_confidence)))

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
    *,
    db: DatabaseService | None = None,
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
                kg_results = await kg_retrieve(
                    query, kg, embedding_service, client, vectors=vector_store
                )
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
                # P2-004: when the grader errors, evaluate_results returns
                # action="grader_unavailable" with reranked results
                # untouched. Surface as a counter so a Haiku outage shows
                # up as crag.grader_failed instead of silently inflating
                # the supplemented bucket / DuckDuckGo hit-rate.
                if crag_result.grading_failed:
                    increment_counter("crag.grader_failed")

            # Apply recency weighting (P5-001) — async since P3-002 because
            # it batch-fetches `memories.confidence` from Postgres.
            weighted_results = await _apply_recency_weighting(crag_result.results, db)

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
                await _track_memory_access(final_results, db)
            except Exception as exc:
                logger.warning("Memory access tracking failed: %s", exc)

            # _format_output's own ``[:top_k]`` is now a defensive no-op
            # because final_results is already capped — pass len() so it
            # does not re-clip the supplemented set.
            return _format_output(
                final_results,
                len(final_results) or top_k,
                grader_unavailable=crag_result.action == "grader_unavailable",
            )

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

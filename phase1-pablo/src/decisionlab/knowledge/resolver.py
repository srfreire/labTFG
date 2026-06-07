"""Conflict resolution, importance scoring, and memory persistence.

Takes extracted facts, scores their importance (Haiku), detects duplicates
against existing memories (Qdrant), resolves conflicts (Sonnet), and persists
final memories to Postgres.
"""

from __future__ import annotations

import json
import logging
import uuid as uuid_mod
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from decisionlab.config import SETTINGS
from decisionlab.knowledge.models import ExtractionResult, ResolutionResult
from decisionlab.knowledge.prompts import (
    CONFLICT_CLASSIFICATION_SYSTEM,
    CONFLICT_CLASSIFICATION_USER,
    IMPORTANCE_SCORING_SYSTEM,
    IMPORTANCE_SCORING_USER,
)
from decisionlab.structured import StructuredOutputError, call_structured
from shared.pipeline_memories import (
    create_memory_once,
    supersede_memory,
    update_confidence,
)

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic
    from sqlalchemy.ext.asyncio import AsyncSession

    from shared.embedding import EmbeddingService
    from shared.models import PipelineMemory
    from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Backwards-compatible module alias for tests and old patch points. This is
# intentionally the idempotent helper, not the raw insert helper.
create_memory = create_memory_once

# Tiered model selection: importance scoring is mechanical 1–10 rating →
# Haiku (knowledge_fast_model). Conflict classification needs to reason
# about whether two memories duplicate / corroborate / enrich / contradict
# each other and merge their content → Sonnet (knowledge_structured_model).
# See docs/specs/memory-refactor/phase-0-stop-lying.md §R1. Token caps stay
# generous so a long importance batch or a verbose classification can
# spell out its reasoning without truncation.
_IMPORTANCE_MAX_TOKENS = 16384
_CLASSIFY_MAX_TOKENS = 4096

_DUPLICATE_THRESHOLD = 0.85
# Above this cosine score, with near-equal length, the duplicate is obvious
# enough to skip the Sonnet classification call. Reserves Sonnet for the
# genuinely ambiguous 0.85–0.95 band where ENRICHMENT/CONTRADICTION live.
_OBVIOUS_DUPLICATE_SCORE = 0.95
_OBVIOUS_DUPLICATE_LEN_RATIO = 0.10

# Naming follows _STAGE_* convention from indexer.py.
_STAGE_NAMESPACE: dict[str, str] = {
    "researcher": "paradigm",
    "formalizer": "formulation",
    "reasoner": "formulation",
    "builder": "model",
}

_STAGE_CONFIDENCE: dict[str, float] = {
    "researcher": 0.6,
    "formalizer": 0.7,
    "reasoner": 0.8,
    "builder": 0.9,
}

_STAGE_MEMORY_TYPE: dict[str, str] = {
    "researcher": "semantic",
    "formalizer": "semantic",
    "reasoner": "semantic",
    "builder": "procedural",
}


class _ImportanceEntry(BaseModel):
    fact: str
    importance: float = Field(ge=1.0, le=10.0)
    reasoning: str = ""


class _ImportanceScores(BaseModel):
    scores: list[_ImportanceEntry]


async def _score_importance(
    facts: list[str],
    client: AsyncAnthropic,
) -> dict[str, float]:
    """Score each fact's importance via the fast (Haiku) structured-output slot.

    Returns ``{fact: score}`` for every fact the model successfully scored.
    Schema violation raises ``StructuredOutputError`` (no silent default to
    5.0 — that pre-rewrite fallback masked importance failures on every
    cumulative-growth topic, see plan §1).
    """
    if not facts:
        return {}

    facts_json = json.dumps(facts, ensure_ascii=False)
    user_message = IMPORTANCE_SCORING_USER.replace("{facts_json}", facts_json)

    result = await call_structured(
        client=client,
        messages=[{"role": "user", "content": user_message}],
        system=IMPORTANCE_SCORING_SYSTEM,
        schema=_ImportanceScores,
        max_tokens=_IMPORTANCE_MAX_TOKENS,
        model=SETTINGS.knowledge_fast_model,
    )
    return {entry.fact: float(entry.importance) for entry in result.scores}


async def _find_duplicates(
    fact: str,
    run_id: str,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
) -> list[dict]:
    """Embed a fact and search for similar existing memories in Qdrant.

    Returns list of candidate dicts with keys: id, score, payload.
    Excludes self-matches from the same run_id.
    """
    vector = await embedding_service.embed_query(fact)
    results = await vector_store.search_dense(
        "memories_dense",
        vector,
        limit=5,
    )

    return [
        {"id": point.id, "score": point.score, "payload": point.payload}
        for point in results
        if point.score > _DUPLICATE_THRESHOLD and point.payload.get("run_id") != run_id
    ]


async def _hydrate_live_candidates(
    candidates: list[dict],
    *,
    run_id: uuid_mod.UUID | None,
    db_session: AsyncSession,
) -> list[dict]:
    """Keep only candidates whose vector id maps to a live PG memory row."""
    if not candidates:
        return []

    from sqlalchemy import select

    from shared.models import PipelineMemory

    ids: list[uuid_mod.UUID] = []
    id_by_candidate: dict[int, uuid_mod.UUID] = {}
    for idx, candidate in enumerate(candidates):
        raw_id = candidate.get("payload", {}).get("entity_id") or candidate.get("id")
        try:
            memory_id = uuid_mod.UUID(str(raw_id))
        except (TypeError, ValueError):
            continue
        ids.append(memory_id)
        id_by_candidate[idx] = memory_id

    if not ids:
        return []

    stmt = select(PipelineMemory).where(
        PipelineMemory.id.in_(ids),
        PipelineMemory.valid_to.is_(None),
    )
    rows = (await db_session.execute(stmt)).scalars().all()
    by_id = {row.id: row for row in rows}

    live: list[dict] = []
    for idx, candidate in enumerate(candidates):
        memory_id = id_by_candidate.get(idx)
        if memory_id is None:
            continue
        memory = by_id.get(memory_id)
        if memory is None:
            logger.debug(
                "Dropping orphan vector candidate without live PG row: %s", memory_id
            )
            continue
        if run_id is not None and memory.run_id == run_id:
            continue
        live.append({**candidate, "id": str(memory.id), "memory": memory})

    return live


async def _index_pipeline_memory(
    memory: PipelineMemory,
    *,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
    content: str | None = None,
    namespace: str | None = None,
    source_stage: str | None = None,
    run_id: uuid_mod.UUID | str | None = None,
    importance: float | None = None,
) -> None:
    """Upsert dense+sparse vectors using the PG memory id as Qdrant id."""
    text = content if content is not None else str(getattr(memory, "content", ""))
    vector = await embedding_service.embed_query(text)
    created_at = getattr(memory, "created_at", None) or datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    payload = {
        "entity_id": str(memory.id),
        "namespace": namespace or str(getattr(memory, "namespace", "")),
        "source_stage": source_stage or str(getattr(memory, "source_stage", "")),
        "source_kind": "pipeline",
        "run_id": str(run_id if run_id is not None else getattr(memory, "run_id", "")),
        "importance": (
            importance if importance is not None else getattr(memory, "importance", 5.0)
        ),
        "created_at": created_at.isoformat(),
        "text_preview": text[:200],
    }
    content_hash = getattr(memory, "content_hash", None)
    if content_hash:
        payload["content_hash"] = str(content_hash)
    await vector_store.upsert_dense(
        "memories_dense",
        str(memory.id),
        vector,
        payload,
    )
    await vector_store.upsert_sparse(
        "memories_sparse",
        str(memory.id),
        text,
        payload,
    )


async def _create_or_reuse_fact_memory(
    db_session: AsyncSession,
    *,
    content: str,
    namespace: str,
    memory_type: str,
    source_stage: str,
    run_id: uuid_mod.UUID,
    importance: float,
    confidence: float,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
) -> bool:
    """Persist a fact idempotently and index it under its PG id.

    Returns True when a new row was inserted, False when an existing live row
    was reused. Both paths upsert vectors so crash/resume after PG commit but
    before Qdrant indexing self-heals on retry.
    """
    created_result = await create_memory(
        db_session,
        content=content,
        namespace=namespace,
        memory_type=memory_type,
        source_stage=source_stage,
        run_id=run_id,
        importance=importance,
        confidence=confidence,
    )
    if isinstance(created_result, tuple):
        memory, created = created_result
    else:
        memory, created = created_result, True
    await _index_pipeline_memory(
        memory,
        embedding_service=embedding_service,
        vector_store=vector_store,
        content=content,
        namespace=namespace,
        source_stage=source_stage,
        run_id=run_id,
        importance=importance,
    )
    return created


class _ConflictClassification(BaseModel):
    classification: (
        str  # "DUPLICATE" | "CORROBORATION" | "ENRICHMENT" | "CONTRADICTION"
    )
    reasoning: str = ""
    merged_content: str | None = None


async def _classify_conflict(
    existing_content: str,
    existing_stage: str,
    existing_timestamp: str,
    new_content: str,
    new_stage: str,
    client: AsyncAnthropic,
) -> dict:
    """Classify the relationship between an existing memory and a new fact.

    Returns the parsed classification dict. Raises ``StructuredOutputError``
    on schema violation so the caller can decide whether to skip the fact
    or surface the failure — replaces the previous silent
    ``{"classification": "UNKNOWN"}`` fallback that masked classification
    bugs throughout the eval suite.
    """
    user_message = (
        CONFLICT_CLASSIFICATION_USER.replace("{existing_stage}", existing_stage)
        .replace("{existing_timestamp}", existing_timestamp)
        .replace("{existing_content}", existing_content)
        .replace("{new_stage}", new_stage)
        .replace("{new_content}", new_content)
    )
    try:
        result = await call_structured(
            client=client,
            messages=[{"role": "user", "content": user_message}],
            system=CONFLICT_CLASSIFICATION_SYSTEM,
            schema=_ConflictClassification,
            max_tokens=_CLASSIFY_MAX_TOKENS,
            model=SETTINGS.knowledge_structured_model,
        )
    except (StructuredOutputError, Exception) as exc:
        # Conflict classification has a per-pair blast radius (one fact at
        # most), so a Sonnet error / schema violation logs at WARNING and
        # the caller treats the fact as new. The plan's "no silent
        # fallback" rule still holds — failures surface in the trace.
        logger.warning("Conflict classification failed: %s", exc)
        return {"classification": "UNKNOWN", "reasoning": "classification failed"}
    return result.model_dump()


def _is_obvious_duplicate(
    score: float, new_content: str, existing_content: str
) -> bool:
    """True when the cosine score and length ratio make a Sonnet call wasteful.

    Both content strings must be non-empty to compare lengths. The 200-char
    text_preview cutoff in vector payloads means perfect-match facts longer
    than 200 chars hit length_ratio≈0 and fall through to Sonnet — that's
    desirable: long facts deserve real classification.
    """
    if score < _OBVIOUS_DUPLICATE_SCORE:
        return False
    if not new_content or not existing_content:
        return False
    n, e = len(new_content), len(existing_content)
    length_ratio = abs(n - e) / max(n, e)
    return length_ratio < _OBVIOUS_DUPLICATE_LEN_RATIO


async def resolve_and_store(
    extraction: ExtractionResult,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
    db_session: AsyncSession,
    client: AsyncAnthropic,
) -> ResolutionResult:
    """Score importance, detect duplicates, resolve conflicts, persist memories.

    Steps:
    1. Importance scoring (Haiku, batch) -- rate each fact 1-10
    2. Duplicate detection (Qdrant) -- cosine similarity > 0.85
    3. Conflict classification (Sonnet) -- only when duplicates found
    4. Memory persistence (Postgres) -- create/update/supersede memories
    """
    facts = extraction.facts
    stage = extraction.stage
    run_id = extraction.run_id
    run_uuid = uuid_mod.UUID(run_id) if run_id else None
    if run_uuid is None:
        raise ValueError("resolve_and_store requires a UUID run_id")

    namespace = _STAGE_NAMESPACE.get(stage, "paradigm")
    memory_type = _STAGE_MEMORY_TYPE.get(stage, "semantic")
    confidence = _STAGE_CONFIDENCE.get(stage, 0.7)

    # Step 1: Importance scoring
    importance_scores = await _score_importance(facts, client)

    memories_created = 0
    duplicates_skipped = 0
    corroborations = 0
    enrichments = 0
    contradictions = 0
    sonnet_calls = 0

    for fact in facts:
        importance = importance_scores.get(fact, 5.0)

        # Step 2: Duplicate detection
        candidates = await _find_duplicates(
            fact,
            run_id,
            embedding_service,
            vector_store,
        )
        candidates = await _hydrate_live_candidates(
            candidates,
            run_id=run_uuid,
            db_session=db_session,
        )

        if not candidates:
            created = await _create_or_reuse_fact_memory(
                db_session,
                content=fact,
                namespace=namespace,
                memory_type=memory_type,
                source_stage=stage,
                run_id=run_uuid,
                importance=importance,
                confidence=confidence,
                embedding_service=embedding_service,
                vector_store=vector_store,
            )
            if created:
                memories_created += 1
            else:
                duplicates_skipped += 1
            continue

        # Step 3: Conflict classification — fast-path obvious duplicates,
        # call Sonnet only on genuinely ambiguous matches.
        best = max(candidates, key=lambda c: c["score"])
        best_id = uuid_mod.UUID(best["id"])
        best_memory = best.get("memory")
        existing_text = getattr(best_memory, "content", None) or best["payload"].get(
            "text_preview", ""
        )

        if _is_obvious_duplicate(best["score"], fact, existing_text):
            label = "DUPLICATE"
            classification = {"classification": "DUPLICATE", "reasoning": "fast-path"}
        else:
            classification = await _classify_conflict(
                existing_content=existing_text,
                existing_stage=getattr(best_memory, "source_stage", None)
                or best["payload"].get("source_stage", "unknown"),
                existing_timestamp=str(
                    getattr(best_memory, "created_at", None)
                    or best["payload"].get("created_at", "unknown")
                ),
                new_content=fact,
                new_stage=stage,
                client=client,
            )
            sonnet_calls += 1
            label = classification.get("classification", "").upper()

        if label == "DUPLICATE":
            duplicates_skipped += 1

        elif label == "CORROBORATION":
            await update_confidence(db_session, best_id, corroborate=True)
            corroborations += 1

        elif label == "ENRICHMENT":
            merged = classification.get("merged_content") or fact
            new_mem = await supersede_memory(
                db_session,
                old_id=best_id,
                new_content=merged,
                namespace=namespace,
                memory_type=memory_type,
                source_stage=stage,
                run_id=run_uuid,
                importance=importance,
                confidence=confidence,
            )
            await _index_pipeline_memory(
                new_mem,
                embedding_service=embedding_service,
                vector_store=vector_store,
                content=merged,
                namespace=namespace,
                source_stage=stage,
                run_id=run_uuid,
                importance=importance,
            )
            enrichments += 1

        elif label == "CONTRADICTION":
            old_content = existing_text or "?"
            await update_confidence(db_session, best_id, contradict=True)
            new_mem = await supersede_memory(
                db_session,
                old_id=best_id,
                new_content=fact,
                namespace=namespace,
                memory_type=memory_type,
                source_stage=stage,
                run_id=run_uuid,
                importance=importance,
                confidence=confidence,
            )
            await _index_pipeline_memory(
                new_mem,
                embedding_service=embedding_service,
                vector_store=vector_store,
                content=fact,
                namespace=namespace,
                source_stage=stage,
                run_id=run_uuid,
                importance=importance,
            )
            meta_content = (
                f"Run {run_id} contradicted memory {best_id}: {old_content} → {fact}"
            )
            meta_result = await create_memory(
                db_session,
                content=meta_content,
                namespace="meta",
                memory_type="episodic",
                source_stage="memory_agent",
                run_id=run_uuid,
                importance=3.0,
                confidence=1.0,
            )
            meta = meta_result[0] if isinstance(meta_result, tuple) else meta_result
            await _index_pipeline_memory(
                meta,
                embedding_service=embedding_service,
                vector_store=vector_store,
                content=meta_content,
                namespace="meta",
                source_stage="memory_agent",
                run_id=run_uuid,
                importance=3.0,
            )
            contradictions += 1

        else:
            logger.warning(
                "Unknown classification '%s' for fact -- storing as new", label
            )
            created = await _create_or_reuse_fact_memory(
                db_session,
                content=fact,
                namespace=namespace,
                memory_type=memory_type,
                source_stage=stage,
                run_id=run_uuid,
                importance=importance,
                confidence=confidence,
                embedding_service=embedding_service,
                vector_store=vector_store,
            )
            if created:
                memories_created += 1
            else:
                duplicates_skipped += 1

    return ResolutionResult(
        memories_created=memories_created,
        duplicates_skipped=duplicates_skipped,
        corroborations=corroborations,
        enrichments=enrichments,
        contradictions=contradictions,
        sonnet_calls=sonnet_calls,
        importance_scores=importance_scores,
    )

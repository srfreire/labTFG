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

from decisionlab.knowledge.models import ExtractionResult, ResolutionResult
from decisionlab.knowledge.prompts import (
    CONFLICT_CLASSIFICATION_SYSTEM,
    CONFLICT_CLASSIFICATION_USER,
    IMPORTANCE_SCORING_SYSTEM,
    IMPORTANCE_SCORING_USER,
)
from decisionlab.runtime.usage import record as record_usage
from shared.memories import create_memory, supersede_memory, update_confidence

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic
    from sqlalchemy.ext.asyncio import AsyncSession

    from shared.embedding import EmbeddingService
    from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)

_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_SONNET_MODEL = "claude-sonnet-4-5-20250514"
_DUPLICATE_THRESHOLD = 0.85

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


async def _score_importance(
    facts: list[str],
    client: AsyncAnthropic,
) -> dict[str, float]:
    """Call Haiku to score importance of each fact. Returns {fact: score}."""
    if not facts:
        return {}

    facts_json = json.dumps(facts, ensure_ascii=False)
    user_message = IMPORTANCE_SCORING_USER.replace("{facts_json}", facts_json)

    try:
        response = await client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=4096,
            system=IMPORTANCE_SCORING_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
        record_usage(_HAIKU_MODEL, getattr(response, "usage", None))
        raw = response.content[0].text if response.content else ""
        scored = json.loads(raw)
        return {
            entry["fact"]: float(entry["importance"])
            for entry in scored
            if isinstance(entry, dict) and "fact" in entry and "importance" in entry
        }
    except Exception:
        logger.warning("Importance scoring failed — defaulting all facts to 5.0", exc_info=True)
        return {fact: 5.0 for fact in facts}


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
        "memories_dense", vector, limit=5,
    )

    return [
        {"id": point.id, "score": point.score, "payload": point.payload}
        for point in results
        if point.score > _DUPLICATE_THRESHOLD and point.payload.get("run_id") != run_id
    ]


async def _classify_conflict(
    existing_content: str,
    existing_stage: str,
    existing_timestamp: str,
    new_content: str,
    new_stage: str,
    client: AsyncAnthropic,
) -> dict:
    """Call Sonnet to classify the relationship between an existing memory and a new fact."""
    user_message = (
        CONFLICT_CLASSIFICATION_USER
        .replace("{existing_stage}", existing_stage)
        .replace("{existing_timestamp}", existing_timestamp)
        .replace("{existing_content}", existing_content)
        .replace("{new_stage}", new_stage)
        .replace("{new_content}", new_content)
    )

    try:
        response = await client.messages.create(
            model=_SONNET_MODEL,
            max_tokens=1024,
            system=CONFLICT_CLASSIFICATION_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
        record_usage(_SONNET_MODEL, getattr(response, "usage", None))
        raw = response.content[0].text if response.content else "{}"
        return json.loads(raw)
    except Exception:
        logger.warning("Conflict classification failed — treating as new fact", exc_info=True)
        return {"classification": "UNKNOWN", "reasoning": "classification failed"}


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
            fact, run_id, embedding_service, vector_store,
        )

        if not candidates:
            await create_memory(
                db_session,
                content=fact,
                namespace=namespace,
                memory_type=memory_type,
                source_stage=stage,
                run_id=run_uuid,
                importance=importance,
                confidence=confidence,
            )
            memories_created += 1
            continue

        # Step 3: Conflict classification (Sonnet) -- use best match
        best = max(candidates, key=lambda c: c["score"])
        best_id = uuid_mod.UUID(best["id"])
        classification = await _classify_conflict(
            existing_content=best["payload"].get("text_preview", ""),
            existing_stage=best["payload"].get("source_stage", "unknown"),
            existing_timestamp=best["payload"].get("created_at", "unknown"),
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
            new_vector = await embedding_service.embed_query(merged)
            await vector_store.upsert_dense(
                "memories_dense",
                str(new_mem.id),
                new_vector,
                {
                    "entity_id": str(new_mem.id),
                    "namespace": namespace,
                    "source_stage": stage,
                    "run_id": run_id,
                    "importance": importance,
                    "confidence": confidence,
                    "created_at": datetime.now(UTC).isoformat(),
                    "text_preview": merged[:200],
                },
            )
            enrichments += 1

        elif label == "CONTRADICTION":
            old_content = best["payload"].get("text_preview", "?")
            await update_confidence(db_session, best_id, contradict=True)
            await supersede_memory(
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
            await create_memory(
                db_session,
                content=(
                    f"Run {run_id} contradicted memory {best_id}: "
                    f"{old_content} → {fact}"
                ),
                namespace="meta",
                memory_type="episodic",
                source_stage="memory_agent",
                run_id=run_uuid,
                importance=3.0,
                confidence=1.0,
            )
            contradictions += 1

        else:
            logger.warning("Unknown classification '%s' for fact -- storing as new", label)
            await create_memory(
                db_session,
                content=fact,
                namespace=namespace,
                memory_type=memory_type,
                source_stage=stage,
                run_id=run_uuid,
                importance=importance,
                confidence=confidence,
            )
            memories_created += 1

    return ResolutionResult(
        memories_created=memories_created,
        duplicates_skipped=duplicates_skipped,
        corroborations=corroborations,
        enrichments=enrichments,
        contradictions=contradictions,
        sonnet_calls=sonnet_calls,
        importance_scores=importance_scores,
    )

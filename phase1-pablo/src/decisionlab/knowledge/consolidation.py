"""Post-run consolidation: cluster, reflect, decay, prune.

Runs after a pipeline run completes. Clusters related memories from the run,
generates higher-level reflections, applies time decay, and prunes stale
knowledge.
"""

from __future__ import annotations

import json
import logging
import time
import uuid as uuid_mod
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np

from decisionlab.config import SETTINGS
from decisionlab.knowledge.models import ConsolidationResult
from decisionlab.knowledge.prompts import (
    CONTRADICTION_CHECK_SYSTEM,
    CONTRADICTION_CHECK_USER,
    REFLECTION_SYSTEM,
    REFLECTION_USER,
)
from decisionlab.runtime.usage import record as record_usage
from shared.memories import apply_time_decay, create_memory, update_confidence

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic
    from sqlalchemy.ext.asyncio import AsyncSession

    from shared.embedding import EmbeddingService
    from shared.knowledge_graph import KnowledgeGraph
    from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)

_FAST_MODEL = SETTINGS.knowledge_fast_model
_CLUSTER_THRESHOLD = 0.80
_REFLECTION_SIMILARITY_THRESHOLD = 0.85
_PRUNE_CONFIDENCE = 0.2
_PRUNE_AGE_DAYS = 90

_REFLECTION_MAX_TOKENS = 4096
_CONTRADICTION_MAX_TOKENS = 4096


async def _call_haiku(
    client: AsyncAnthropic,
    *,
    system: str,
    user: str,
    max_tokens: int,
) -> str:
    """Single Haiku call. Raises on output truncation so callers can't silently
    swallow a partial response as a JSON parse error. Streams when ``max_tokens``
    is large enough to risk the SDK's 10-minute non-streaming guard."""
    if max_tokens >= 8192:
        async with client.messages.stream(
            model=_FAST_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            response = await stream.get_final_message()
    else:
        response = await client.messages.create(
            model=_FAST_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    record_usage(_FAST_MODEL, getattr(response, "usage", None))

    if getattr(response, "stop_reason", None) == "max_tokens":
        usage = getattr(response, "usage", None)
        out_tokens = getattr(usage, "output_tokens", None) if usage else None
        raise RuntimeError(
            f"Haiku output truncated at max_tokens={max_tokens} "
            f"(output_tokens={out_tokens})"
        )

    if not response.content:
        return ""
    return response.content[0].text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def consolidate(
    db_session: AsyncSession,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
    client: AsyncAnthropic,
    run_id: str,
    kg: KnowledgeGraph | None = None,
) -> ConsolidationResult:
    """Run post-run consolidation pipeline.

    Steps:
      1. Cluster related memories from the completed run
      2. Generate reflections for clusters of >=3 memories
      3. Apply time decay to all stale memories
      4. Prune memories with low confidence, zero access, and age > 90 days

    When *kg* is provided, generated reflections are also written to the
    knowledge graph as Reflection nodes so graph-traversal retrievers see them.
    """
    t0 = time.monotonic()

    # Step 1: Cluster
    clusters = await _cluster_run_memories(
        db_session,
        embedding_service,
        run_id,
    )

    # Step 2: Reflections
    reflections_generated, reflections_corroborated = await _generate_reflections(
        db_session,
        embedding_service,
        vector_store,
        client,
        clusters,
        run_id,
        kg=kg,
    )

    # Step 3: Time decay
    memories_decayed = await _apply_decay_and_sync(
        db_session,
        vector_store,
    )

    # Step 4: Prune
    memories_pruned = await _prune_stale(db_session)

    await db_session.commit()

    duration_ms = int((time.monotonic() - t0) * 1000)
    return ConsolidationResult(
        clusters_found=len(clusters),
        reflections_generated=reflections_generated,
        reflections_corroborated=reflections_corroborated,
        memories_decayed=memories_decayed,
        memories_pruned=memories_pruned,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Step 1: Cluster related memories
# ---------------------------------------------------------------------------


async def _cluster_run_memories(
    session: AsyncSession,
    embedding_service: EmbeddingService,
    run_id: str,
) -> list[list[object]]:
    """Load run memories, embed, and cluster by cosine similarity."""
    from sqlalchemy import and_, select

    from shared.models import Memory

    stmt = select(Memory).where(
        and_(
            Memory.run_id == uuid_mod.UUID(run_id),
            Memory.valid_to.is_(None),
        ),
    )
    result = await session.execute(stmt)
    memories = list(result.scalars().all())

    if len(memories) < 2:
        return []

    texts = [m.content for m in memories]
    vectors = await embedding_service.embed_texts(texts)
    arr = np.array(vectors, dtype=np.float32)

    # Normalize for cosine similarity
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    arr = arr / norms

    # Pairwise cosine similarity
    sim_matrix = arr @ arr.T

    # Single-linkage clustering
    n = len(memories)
    cluster_ids = list(range(n))

    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] > _CLUSTER_THRESHOLD:
                _merge_clusters(cluster_ids, i, j)

    # Group memories by cluster
    groups: dict[int, list[object]] = {}
    for idx, mem in enumerate(memories):
        root = _find_root(cluster_ids, idx)
        groups.setdefault(root, []).append(mem)

    # Only return clusters with 2+ members
    return [mems for mems in groups.values() if len(mems) >= 2]


def _find_root(parents: list[int], i: int) -> int:
    while parents[i] != i:
        parents[i] = parents[parents[i]]
        i = parents[i]
    return i


def _merge_clusters(parents: list[int], a: int, b: int) -> None:
    ra, rb = _find_root(parents, a), _find_root(parents, b)
    if ra != rb:
        parents[rb] = ra


# ---------------------------------------------------------------------------
# Step 2: Generate reflections
# ---------------------------------------------------------------------------


async def _generate_reflections(
    session: AsyncSession,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
    client: AsyncAnthropic,
    clusters: list[list[object]],
    run_id: str,
    kg: KnowledgeGraph | None = None,
) -> tuple[int, int]:
    """Generate reflection memories from clusters of >=3 and detect cross-run patterns."""
    reflections_generated = 0
    reflections_corroborated = 0

    # Filter to clusters with >=3 memories
    large_clusters = [c for c in clusters if len(c) >= 3]

    for cluster in large_clusters:
        # Build prompt with numbered facts
        numbered = "\n".join(f"{i + 1}. {mem.content}" for i, mem in enumerate(cluster))
        user_msg = REFLECTION_USER.replace("{numbered_facts}", numbered)

        try:
            raw = await _call_haiku(
                client,
                system=REFLECTION_SYSTEM,
                user=user_msg,
                max_tokens=_REFLECTION_MAX_TOKENS,
            )
            insights = json.loads(raw or "[]")
        except Exception as exc:
            logger.warning(
                "Reflection generation failed for cluster (size=%d), skipping: %s",
                len(cluster), exc,
            )
            continue

        if not isinstance(insights, list):
            continue

        source_ids = [str(mem.id) for mem in cluster]

        for insight_text in insights:
            if not isinstance(insight_text, str) or not insight_text.strip():
                continue

            # Store reflection memory
            reflection = await create_memory(
                session,
                content=insight_text.strip(),
                namespace="meta",
                memory_type="reflection",
                source_stage="consolidation",
                run_id=uuid_mod.UUID(run_id),
                importance=8.0,
                confidence=0.7,
                metadata_={"source_memories": source_ids},
            )
            reflections_generated += 1

            # Embed and index the new reflection
            vectors = await embedding_service.embed_texts([reflection.content])
            point_id = str(reflection.id)
            await vector_store.upsert_dense(
                collection="memories_dense",
                id=point_id,
                vector=vectors[0],
                payload={
                    "entity_id": point_id,
                    "namespace": "meta",
                    "source_stage": "consolidation",
                    "run_id": run_id,
                    "importance": 8.0,
                    "confidence": 0.7,
                    "created_at": datetime.now(UTC).isoformat(),
                    "text_preview": reflection.content[:200],
                },
            )

            # Mirror the reflection into the KG so graph traversals can reach
            # cross-run synthesis. Failures are non-fatal — vectors + Postgres
            # remain the source of truth.
            if kg is not None:
                try:
                    await kg.create_node(
                        "Reflection",
                        {
                            "id": point_id,
                            "content": reflection.content,
                            "run_id": run_id,
                            "source_memory_ids": source_ids,
                            "created_at": datetime.now(UTC).isoformat(),
                        },
                    )
                except Exception:
                    logger.warning(
                        "Failed to mirror reflection %s to KG", point_id,
                        exc_info=True,
                    )

            # Cross-run: compare against existing reflections
            corroborated = await _check_cross_run_reflections(
                session,
                embedding_service,
                vector_store,
                client,
                reflection,
                vectors[0],
                run_id,
            )
            reflections_corroborated += corroborated

    return reflections_generated, reflections_corroborated


async def _check_cross_run_reflections(
    session: AsyncSession,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
    client: AsyncAnthropic,
    new_reflection: object,
    embedding: list[float],
    run_id: str,
) -> int:
    """Compare a new reflection against existing reflections from past runs."""
    # Search for similar existing reflections
    similar = await vector_store.search_dense(
        collection="memories_dense",
        vector=embedding,
        limit=5,
        filters={"namespace": "meta"},
    )

    corroborated = 0
    for point in similar:
        # Skip self and same-run results
        if point.id == str(new_reflection.id):
            continue
        if point.payload.get("run_id") == run_id:
            continue
        if point.score < _REFLECTION_SIMILARITY_THRESHOLD:
            continue

        # High similarity found — check if contradiction or corroboration
        existing_text = point.payload.get("text_preview", "")
        is_contradiction = await _is_contradiction(
            client,
            existing_text,
            new_reflection.content,
        )

        if is_contradiction:
            logger.info(
                "Contradiction detected between reflections: %s vs %s",
                point.id,
                new_reflection.id,
            )
        else:
            # Corroborate the existing reflection
            try:
                await update_confidence(
                    session,
                    uuid_mod.UUID(point.id),
                    corroborate=True,
                )
                corroborated += 1
            except Exception:
                logger.warning("Failed to corroborate reflection %s", point.id)

    return corroborated


async def _is_contradiction(
    client: AsyncAnthropic,
    text_a: str,
    text_b: str,
) -> bool:
    """Use Haiku to check if two reflections contradict each other."""
    user_msg = CONTRADICTION_CHECK_USER.replace("{reflection_a}", text_a).replace(
        "{reflection_b}", text_b
    )
    try:
        raw = await _call_haiku(
            client,
            system=CONTRADICTION_CHECK_SYSTEM,
            user=user_msg,
            max_tokens=_CONTRADICTION_MAX_TOKENS,
        )
        parsed = json.loads(raw or "{}")
        return parsed.get("contradicts", False) is True
    except Exception as exc:
        logger.warning(
            "Contradiction check failed, assuming no contradiction: %s", exc
        )
        return False


# ---------------------------------------------------------------------------
# Step 3: Time decay + Qdrant sync
# ---------------------------------------------------------------------------


async def _apply_decay_and_sync(
    session: AsyncSession,
    vector_store: VectorStore,
) -> int:
    """Apply time decay via shared helper, then sync confidence to Qdrant."""
    from sqlalchemy import and_, select

    from shared.models import Memory

    # Collect pre-decay confidences for changed memories. The DateTime columns
    # on Memory are TIMESTAMP WITHOUT TIME ZONE (naive), so the cutoff bound
    # against them must also be naive — asyncpg refuses to compare aware vs
    # naive in the same query.
    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now - timedelta(days=30)

    stmt = select(Memory.id, Memory.confidence).where(
        and_(
            Memory.valid_to.is_(None),
            Memory.memory_type != "reflection",
            Memory.last_accessed_at < cutoff,
            Memory.last_accessed_at.isnot(None),
        ),
    )
    result = await session.execute(stmt)
    pre_decay = {row.id: row.confidence for row in result.all()}

    # Apply decay
    count = await apply_time_decay(session)

    # Sync updated confidences to Qdrant
    if count > 0:
        # Re-read the decayed memories to get new confidence values
        stmt = select(Memory.id, Memory.confidence).where(
            Memory.id.in_(list(pre_decay.keys())),
        )
        result = await session.execute(stmt)
        for row in result.all():
            if row.confidence != pre_decay.get(row.id):
                try:
                    await vector_store.set_payload(
                        collection="memories_dense",
                        id=str(row.id),
                        payload={"confidence": row.confidence},
                    )
                except Exception:
                    logger.debug(
                        "Could not sync confidence to Qdrant for %s",
                        row.id,
                    )

    return count


# ---------------------------------------------------------------------------
# Step 4: Prune stale memories
# ---------------------------------------------------------------------------


async def _prune_stale(session: AsyncSession) -> int:
    """Soft-delete memories with low confidence, zero access, and age > 90 days."""
    from sqlalchemy import and_, select, update

    from shared.models import Memory

    # Naive UTC: see comment in `_apply_decay_and_sync`. `now` ends up bound
    # both against `created_at` (cutoff comparison) and stored in `valid_to`
    # (soft-delete marker), so it has to match the column timezone-naivete.
    now = datetime.now(UTC).replace(tzinfo=None)
    age_cutoff = now - timedelta(days=_PRUNE_AGE_DAYS)

    stmt = select(Memory.id).where(
        and_(
            Memory.confidence < _PRUNE_CONFIDENCE,
            Memory.access_count == 0,
            Memory.created_at < age_cutoff,
            Memory.valid_to.is_(None),
        ),
    )
    result = await session.execute(stmt)
    ids_to_prune = [row.id for row in result.all()]

    if not ids_to_prune:
        return 0

    upd = update(Memory).where(Memory.id.in_(ids_to_prune)).values(valid_to=now)
    await session.execute(upd)
    await session.flush()

    logger.info("Pruned %d stale memories", len(ids_to_prune))
    return len(ids_to_prune)

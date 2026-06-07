"""One-shot repair for Phase 1 memory vector IDs.

After the PG-first memory fix, Qdrant memory points must use
``pipeline_memories.id`` as both the point id and payload ``entity_id``.
Older runs wrote deterministic run/stage/chunk UUIDs before the PG row
existed, leaving orphan vector points outside lifecycle governance.

This script:

  1. Reads every live Phase 1 ``pipeline_memories`` row except KG relation
     rows.
  2. Upserts dense and sparse points under the PG memory id.
  3. Deletes Qdrant points marked ``source_kind='pipeline'`` whose id is not
     a live PG memory id.

Seed paradigm vectors and Phase 2 simulation observations are preserved.

Usage:

    uv run scripts/qdrant_reindex_pipeline_memories.py --dry-run
    uv run scripts/qdrant_reindex_pipeline_memories.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from shared.knowledge_graph import KG_RELATION_NAMESPACE
from shared.models import PipelineMemory
from shared.services import init_services, shutdown_services

logger = logging.getLogger(__name__)

COLLECTIONS = ("memories_dense", "memories_sparse")
SCROLL_BATCH = 512
EMBED_BATCH = 64


def _created_at_iso(memory: PipelineMemory) -> str:
    created_at = memory.created_at or datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at.isoformat()


def _payload(memory: PipelineMemory) -> dict:
    payload = {
        "entity_id": str(memory.id),
        "namespace": memory.namespace,
        "source_stage": memory.source_stage,
        "source_kind": "pipeline",
        "run_id": str(memory.run_id),
        "importance": memory.importance,
        "created_at": _created_at_iso(memory),
        "text_preview": memory.content[:200],
    }
    if memory.content_hash:
        payload["content_hash"] = memory.content_hash
    return payload


async def _live_pipeline_memories(services) -> list[PipelineMemory]:
    async with services.db.get_session() as session:
        rows = await session.execute(
            select(PipelineMemory)
            .where(PipelineMemory.valid_to.is_(None))
            .where(PipelineMemory.namespace != KG_RELATION_NAMESPACE)
            .order_by(PipelineMemory.created_at.asc())
        )
        return list(rows.scalars().all())


async def _reindex(memories: list[PipelineMemory], *, dry_run: bool, services) -> int:
    if services.embeddings is None or services.vectors is None:
        raise RuntimeError("Embeddings and VectorStore are required")

    if dry_run:
        return len(memories)

    indexed = 0
    for start in range(0, len(memories), EMBED_BATCH):
        batch = memories[start : start + EMBED_BATCH]
        vectors = await services.embeddings.embed_texts([m.content for m in batch])
        if len(vectors) != len(batch):
            raise RuntimeError(
                f"embed_texts returned {len(vectors)} vectors for {len(batch)} rows"
            )
        for memory, vector in zip(batch, vectors, strict=True):
            if not dry_run:
                payload = _payload(memory)
                await services.vectors.upsert_dense(
                    "memories_dense",
                    str(memory.id),
                    vector,
                    payload,
                )
                await services.vectors.upsert_sparse(
                    "memories_sparse",
                    str(memory.id),
                    memory.content,
                    payload,
                )
            indexed += 1
    return indexed


def _is_pipeline_point(payload: dict | None) -> bool:
    if not payload:
        return False
    if payload.get("source_stage") == "seed":
        return False
    if payload.get("run_id") == "canonical-paradigms-seed":
        return False
    if payload.get("source_kind") == "simulation":
        return False
    if payload.get("namespace") == "simulation":
        return False
    return payload.get("source_kind") == "pipeline"


async def _delete_orphans(
    collection: str,
    *,
    live_ids: set[str],
    dry_run: bool,
    services,
) -> int:
    if services.vectors is None:
        raise RuntimeError("VectorStore is required")

    client = services.vectors._c()
    deleted = 0
    offset: object | None = None
    while True:
        points, offset = await client.scroll(
            collection_name=collection,
            limit=SCROLL_BATCH,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break

        orphan_ids = []
        for point in points:
            point_id = str(point.id)
            if point_id in live_ids:
                continue
            if _is_pipeline_point(point.payload):
                try:
                    uuid.UUID(point_id)
                except ValueError:
                    continue
                orphan_ids.append(point_id)

        if orphan_ids and not dry_run:
            await services.vectors.delete(collection, orphan_ids)
        deleted += len(orphan_ids)

        if offset is None:
            break
    return deleted


async def _main(*, dry_run: bool) -> None:
    services = await init_services()
    try:
        memories = await _live_pipeline_memories(services)
        live_ids = {str(memory.id) for memory in memories}
        indexed = await _reindex(memories, dry_run=dry_run, services=services)
        logger.info(
            "qdrant_reindex_pipeline_memories: %s %d live PG memories",
            "would reindex" if dry_run else "reindexed",
            indexed,
        )
        for collection in COLLECTIONS:
            deleted = await _delete_orphans(
                collection,
                live_ids=live_ids,
                dry_run=dry_run,
                services=services,
            )
            logger.info(
                "qdrant_reindex_pipeline_memories: %s %d orphan points from %s",
                "would delete" if dry_run else "deleted",
                deleted,
                collection,
            )
    finally:
        await shutdown_services(services)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    asyncio.run(_main(dry_run=args.dry_run))

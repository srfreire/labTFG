"""Backfill PG memory IDs for legacy ``kg_health`` Neo4j edges.

Older readability repairs created conservative KG edges with
``source='kg_health'`` but no ``memory_id``.  After the PG-first memory fix,
health-created edges must point at ``pipeline_memories`` rows so lifecycle
filters, time travel and retrieval all agree on relation validity.

This script:

  1. Creates/reuses a deterministic backfill ``runs`` row.
  2. Creates/reuses one ``pipeline_memories`` row per legacy health edge.
  3. Stamps the Neo4j edge with ``r.memory_id``.

Usage:

    uv run scripts/kg_backfill_health_relation_memories.py --dry-run
    uv run scripts/kg_backfill_health_relation_memories.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update

from decisionlab.knowledge.kg_writer import (
    _DEFAULT_RELATION_CONFIDENCE,
    _DEFAULT_RELATION_IMPORTANCE,
    _STAGE_RELATION_CONFIDENCE,
    _STAGE_RELATION_IMPORTANCE,
    _relation_content,
)
from shared.knowledge_graph import KG_RELATION_NAMESPACE, KnowledgeGraph
from shared.models import PipelineMemory, Run
from shared.pipeline_memories import create_memory_once
from shared.services import init_services, shutdown_services

logger = logging.getLogger(__name__)

_BACKFILL_RUN_ID = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "labtfg.phase1.kg_health_relation_memory_backfill",
)
_BACKFILL_STAGE = "kg_health_backfill"


def _label(labels: list[str]) -> str | None:
    for label in labels:
        if label in KnowledgeGraph.SCHEMA:
            return label
    return labels[0] if labels else None


def _identity(label: str, props: dict[str, Any]) -> tuple[str, str]:
    try:
        unique_key = KnowledgeGraph.unique_key_for(label)
    except ValueError:
        unique_key = ""
    keys = [unique_key, "slug", "id", "doi", "name", "title", "latex"]
    for key in keys:
        if not key:
            continue
        value = props.get(key)
        if value is not None and str(value).strip():
            return key, str(value)
    return "_unknown", "<unknown>"


async def _scan_legacy_health_edges(kg: KnowledgeGraph) -> list[dict[str, Any]]:
    return await kg.query(
        "MATCH (a)-[r]->(b) "
        "WHERE r.source = 'kg_health' AND r.memory_id IS NULL "
        "RETURN elementId(r) AS rid, type(r) AS rel_type, "
        "labels(a) AS from_labels, properties(a) AS from_props, "
        "labels(b) AS to_labels, properties(b) AS to_props, "
        "properties(r) AS rel_props "
        "ORDER BY rid"
    )


async def _ensure_backfill_run(services, *, target_edges: int) -> None:
    async with services.db.get_session() as session:
        existing = await session.get(Run, _BACKFILL_RUN_ID)
        if existing is None:
            session.add(
                Run(
                    id=_BACKFILL_RUN_ID,
                    problem_description=(
                        "Backfill PG memory IDs for legacy kg_health Neo4j edges"
                    ),
                    status="running",
                    kind="prod",
                    s3_prefix=f"backfills/kg-health/{_BACKFILL_RUN_ID}",
                    artifact_count=0,
                    final_stage=_BACKFILL_STAGE,
                    memory_results={"target_edges": target_edges},
                )
            )
        else:
            existing.status = "running"
            existing.final_stage = _BACKFILL_STAGE
            existing.memory_results = {"target_edges": target_edges}
        await session.commit()


async def _finish_backfill_run(
    services,
    *,
    target_edges: int,
    migrated: int,
    skipped: int,
) -> None:
    async with services.db.get_session() as session:
        await session.execute(
            update(Run)
            .where(Run.id == _BACKFILL_RUN_ID)
            .values(
                status="done",
                artifact_count=0,
                final_stage=_BACKFILL_STAGE,
                memory_results={
                    "target_edges": target_edges,
                    "migrated": migrated,
                    "skipped": skipped,
                },
            )
        )
        await session.commit()


async def _delete_memory(services, memory_id: uuid.UUID) -> None:
    async with services.db.get_session() as session:
        memory = await session.get(PipelineMemory, memory_id)
        if memory is not None:
            await session.delete(memory)
        await session.commit()


async def _create_edge_memory(services, row: dict[str, Any]) -> tuple[uuid.UUID, bool]:
    from_label = _label(row["from_labels"])
    to_label = _label(row["to_labels"])
    if from_label is None or to_label is None:
        raise ValueError("relation endpoint has no label")

    _from_key, from_value = _identity(from_label, dict(row["from_props"]))
    _to_key, to_value = _identity(to_label, dict(row["to_props"]))
    rel_props = dict(row["rel_props"] or {})
    stage = str(rel_props.get("source_stage") or _BACKFILL_STAGE)[:100]
    valid_from = datetime.now(UTC).replace(tzinfo=None)

    content = _relation_content(
        from_label=from_label,
        from_key_value=from_value,
        rel_type=str(row["rel_type"]),
        to_label=to_label,
        to_key_value=to_value,
    )
    metadata = {
        **rel_props,
        "backfill": _BACKFILL_STAGE,
        "backfilled_at": datetime.now(UTC).isoformat(),
    }

    async with services.db.get_session() as session:
        memory, created = await create_memory_once(
            session,
            content=content,
            namespace=KG_RELATION_NAMESPACE,
            memory_type="semantic",
            source_stage=stage,
            run_id=_BACKFILL_RUN_ID,
            importance=_STAGE_RELATION_IMPORTANCE.get(
                stage, _DEFAULT_RELATION_IMPORTANCE
            ),
            confidence=_STAGE_RELATION_CONFIDENCE.get(
                stage, _DEFAULT_RELATION_CONFIDENCE
            ),
            valid_from=valid_from,
            metadata_=metadata,
        )
        await session.commit()
        return memory.id, created


async def _stamp_edge(kg: KnowledgeGraph, *, rid: str, memory_id: uuid.UUID) -> bool:
    rows = await kg.query(
        "MATCH ()-[r]->() "
        "WHERE elementId(r) = $rid "
        "AND r.source = 'kg_health' "
        "AND r.memory_id IS NULL "
        "SET r.memory_id = $memory_id "
        "RETURN count(r) AS updated",
        {"rid": rid, "memory_id": str(memory_id)},
    )
    return bool(rows and rows[0].get("updated"))


async def _backfill(*, dry_run: bool) -> tuple[int, int, int]:
    services = await init_services()
    try:
        if services.kg is None:
            raise RuntimeError("Neo4j is required")

        rows = await _scan_legacy_health_edges(services.kg)
        seen = len(rows)
        migrated = 0
        skipped = 0
        if dry_run or seen == 0:
            return seen, seen if dry_run else 0, 0

        await _ensure_backfill_run(services, target_edges=seen)
        for row in rows:
            try:
                memory_id, created = await _create_edge_memory(services, row)
                stamped = await _stamp_edge(
                    services.kg,
                    rid=str(row["rid"]),
                    memory_id=memory_id,
                )
                if stamped:
                    migrated += 1
                elif created:
                    await _delete_memory(services, memory_id)
                    skipped += 1
                else:
                    skipped += 1
            except Exception as exc:
                skipped += 1
                logger.warning(
                    "kg_health backfill skipped rid=%s: %s",
                    row.get("rid"),
                    exc,
                )

        await _finish_backfill_run(
            services,
            target_edges=seen,
            migrated=migrated,
            skipped=skipped,
        )
        return seen, migrated, skipped
    finally:
        await shutdown_services(services)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    seen, migrated, skipped = asyncio.run(_backfill(dry_run=args.dry_run))
    action = "would migrate" if args.dry_run else "migrated"
    logger.info(
        "kg_backfill_health_relation_memories: seen=%d %s=%d skipped=%d",
        seen,
        action,
        migrated,
        skipped,
    )

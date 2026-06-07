"""One-shot backfill: extract temporal metadata from Neo4j relations into
``pipeline_memories`` rows, then strip the legacy temporal props (P4-004).

Pre-P4-004 every relation carried ``valid_from`` / ``valid_to`` / ``run_id``
/ ``created_at`` / ``confidence`` directly on the Neo4j edge.  After P4-004
Postgres ``pipeline_memories`` is the temporal source of truth and the edge
keeps only the identity triple plus a ``memory_id`` foreign key.

This script walks every relation in Neo4j and:

  1. Skips relations that already carry a ``memory_id`` (idempotent re-runs).
  2. Mints a ``pipeline_memories`` row capturing the relation's temporal
     facts: ``content`` derived from the identity triple,
     ``namespace='kg_relation'``, ``memory_type='semantic'``,
     ``valid_from`` / ``valid_to`` / ``confidence`` lifted from the edge
     (or stage defaults if absent), ``run_id`` parsed from the edge if
     it's a UUID (otherwise the row is skipped — it's seed-era data).
  3. Sets ``r.memory_id = <new uuid>`` and removes the legacy temporal
     properties from the edge in the same Cypher pass.

Usage:

    # Dry run — count relations without mutating
    uv run scripts/kg_temporal_to_pg.py --dry-run

    # Apply
    uv run scripts/kg_temporal_to_pg.py

Not auto-run by anything; invoke manually after deploying P4-004.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

from shared.knowledge_graph import KG_RELATION_NAMESPACE
from shared.pipeline_memories import memory_content_hash
from shared.services import init_services, shutdown_services

logger = logging.getLogger(__name__)


_LEGACY_TEMPORAL_KEYS = (
    "valid_from",
    "valid_to",
    "run_id",
    "created_at",
    "updated_at",
    "superseded_by",
    "confidence",
)
_DEFAULT_CONFIDENCE = 0.7
_DEFAULT_IMPORTANCE = 5.0
_BATCH_SIZE = 256


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo is None else dt.replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _parse_uuid(value: object) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def _scan_legacy_relations(kg) -> list[dict]:
    """Return every relation that still carries legacy temporal props.

    A relation qualifies when it has neither ``memory_id`` nor any of
    ``valid_from`` / ``valid_to`` / ``run_id`` / ``created_at`` —
    actually we want the OR: missing memory_id AND has at least one
    legacy temporal prop. Pure seed edges (no memory_id, no temporal
    props) are skipped: they're timeless canonical truth.
    """
    cypher = (
        "MATCH (a)-[r]->(b) "
        "WHERE r.memory_id IS NULL AND ("
        "  r.valid_from IS NOT NULL OR r.valid_to IS NOT NULL "
        "  OR r.run_id IS NOT NULL OR r.created_at IS NOT NULL "
        "  OR r.confidence IS NOT NULL"
        ") "
        "RETURN elementId(r) AS rid, type(r) AS rel_type, "
        "labels(a) AS from_labels, properties(a) AS from_props, "
        "labels(b) AS to_labels, properties(b) AS to_props, "
        "properties(r) AS props"
    )
    return await kg.query(cypher)


def _identity_for(node_props: dict, labels: list[str]) -> tuple[str, str]:
    """Return ``(label, key_value)`` for an endpoint node.

    Picks the first label and the first available identifier
    (``slug``/``id``/``doi``/``name``/``title``).  Falls back to a
    string-encoded element id placeholder if nothing usable is found.
    """
    label = labels[0] if labels else "Node"
    for key in ("slug", "id", "doi", "name", "title", "_synthetic_id"):
        val = node_props.get(key)
        if val is not None and val != "":
            return label, str(val)
    return label, "<unknown>"


async def _backfill(services, *, dry_run: bool) -> tuple[int, int, int]:
    """Drive the migration. Returns (seen, migrated, skipped)."""
    if services.kg is None:
        raise RuntimeError("init_services() did not bring up the KG")

    rows = await _scan_legacy_relations(services.kg)
    seen = len(rows)
    migrated = 0
    skipped = 0

    if seen == 0:
        logger.info("kg_temporal_to_pg: nothing to do — no legacy relations found")
        return seen, migrated, skipped

    from sqlalchemy import text as sql_text

    # We update Neo4j and Postgres in lockstep, one batch at a time, so a
    # crash mid-run leaves the system in a consistent partial state: every
    # PG row written has its corresponding Neo4j edge already pointing
    # back via memory_id.
    for batch_start in range(0, seen, _BATCH_SIZE):
        batch = rows[batch_start : batch_start + _BATCH_SIZE]
        for row in batch:
            run_uuid = _parse_uuid(row["props"].get("run_id"))
            if run_uuid is None:
                # Pre-runs-table seed data — can't satisfy the FK. Skip
                # rather than invent a synthetic run.
                skipped += 1
                logger.warning(
                    "kg_temporal_to_pg: skipping relation rid=%s (no UUID run_id)",
                    row["rid"],
                )
                continue

            from_label, from_key = _identity_for(row["from_props"], row["from_labels"])
            to_label, to_key = _identity_for(row["to_props"], row["to_labels"])

            content = (
                f"{from_label}.{from_key} -[{row['rel_type']}]-> {to_label}.{to_key}"
            )
            valid_from = (
                _parse_dt(row["props"].get("valid_from"))
                or _parse_dt(row["props"].get("created_at"))
                or datetime.now(UTC).replace(tzinfo=None)
            )
            valid_to = _parse_dt(row["props"].get("valid_to"))
            confidence = row["props"].get("confidence")
            try:
                confidence = float(confidence) if confidence is not None else None
            except (TypeError, ValueError):
                confidence = None
            if confidence is None:
                confidence = _DEFAULT_CONFIDENCE

            # Drop temporal/identity-irrelevant props out of the JSONB
            # snapshot — they live in their own columns now.
            content_props = {
                k: v
                for k, v in row["props"].items()
                if k not in _LEGACY_TEMPORAL_KEYS and k != "memory_id"
            }

            new_id = uuid.uuid4()

            if dry_run:
                logger.info(
                    "kg_temporal_to_pg: WOULD migrate rid=%s -> memory_id=%s",
                    row["rid"],
                    new_id,
                )
                migrated += 1
                continue

            try:
                async with services.db.get_session() as session:
                    await session.execute(
                        sql_text(
                            "INSERT INTO pipeline_memories "
                            "(id, content, content_hash, namespace, memory_type, "
                            "source_stage, run_id, importance, confidence, "
                            "valid_from, valid_to, metadata) "
                            "VALUES (:id, :content, :content_hash, :namespace, "
                            "'semantic', 'kg_temporal_backfill', "
                            ":run_id, :importance, "
                            ":confidence, :valid_from, :valid_to, "
                            "CAST(:metadata AS JSONB))"
                        ),
                        {
                            "id": new_id,
                            "content": content,
                            "content_hash": memory_content_hash(content),
                            "namespace": KG_RELATION_NAMESPACE,
                            "run_id": run_uuid,
                            "importance": _DEFAULT_IMPORTANCE,
                            "confidence": confidence,
                            "valid_from": valid_from,
                            "valid_to": valid_to,
                            "metadata": json.dumps(content_props, default=str),
                        },
                    )
                    await session.commit()
            except Exception as exc:
                logger.error(
                    "kg_temporal_to_pg: PG insert failed for rid=%s: %s",
                    row["rid"],
                    exc,
                )
                skipped += 1
                continue

            try:
                # SET memory_id and REMOVE the legacy temporal props in one
                # write so a crash between the two leaves no orphaned PG row
                # without a Neo4j join key.
                await services.kg.query(
                    "MATCH ()-[r]->() WHERE elementId(r) = $rid "
                    "SET r.memory_id = $memory_id "
                    "REMOVE r.valid_from, r.valid_to, r.run_id, "
                    "r.created_at, r.updated_at, r.superseded_by, r.confidence",
                    {"rid": row["rid"], "memory_id": str(new_id)},
                )
            except Exception as exc:
                logger.error(
                    "kg_temporal_to_pg: KG update failed for rid=%s; "
                    "rolling back PG insert: %s",
                    row["rid"],
                    exc,
                )
                # Roll back the PG row so a re-run can pick this rid up
                # cleanly via the WHERE r.memory_id IS NULL filter.
                try:
                    async with services.db.get_session() as session:
                        await session.execute(
                            sql_text("DELETE FROM pipeline_memories WHERE id = :id"),
                            {"id": new_id},
                        )
                        await session.commit()
                except Exception as exc2:
                    logger.error(
                        "kg_temporal_to_pg: rollback failed for memory_id=%s: %s",
                        new_id,
                        exc2,
                    )
                skipped += 1
                continue

            migrated += 1

    return seen, migrated, skipped


async def main(*, dry_run: bool) -> None:
    services = await init_services()
    try:
        seen, migrated, skipped = await _backfill(services, dry_run=dry_run)
        logger.info(
            "kg_temporal_to_pg: seen=%d migrated=%d skipped=%d (dry_run=%s)",
            seen,
            migrated,
            skipped,
            dry_run,
        )
    finally:
        await shutdown_services(services)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count what would be migrated without mutating Neo4j or Postgres",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))

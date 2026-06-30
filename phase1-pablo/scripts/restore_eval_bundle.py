"""Restore a Phase-1 eval *artifact bundle* into the local backend.

Reverse of :mod:`decisionlab.eval.export`. Takes a bundle produced by
``export_suite_artifacts`` (the directory committed under
``evals/reports/<date>-<suite>/artifact-bundle``) and rehydrates it into the
running stack so the Phase-2 lab can simulate, observe, analyse and report on
the generated models:

  * **Postgres** — ``runs``, ``models``, ``artifacts``,
    ``node_run_observations`` and ``pipeline_memories`` rows from
    ``database/*.json``.
  * **MinIO** — every file under ``storage/`` uploaded at its S3 key (the path
    relative to ``storage/``, which is exactly what ``s3_model_key`` /
    ``s3_key`` reference).
  * **Neo4j** — the KG ``kg_snapshot_*.json`` via :func:`kgadmin.restore`.
  * **Qdrant** — dense + sparse vectors re-embedded from the restored
    ``pipeline_memories`` (the bundle ships no vector snapshot).

By default the target stores are **wiped first** (one case at a time). The
embedding keys live in ``phase2-juan/.env``; this script loads that file so the
dense re-index has a Voyage key.

Usage::

    uv run scripts/restore_eval_bundle.py \\
        ../evals/reports/2026-06-29-caso1-pdf-corpus/artifact-bundle
    uv run scripts/restore_eval_bundle.py <bundle> --no-wipe   # layer on top
    uv run scripts/restore_eval_bundle.py <bundle> --dry-run   # plan only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

from decisionlab.eval import kgadmin
from shared.models import (
    Artifact,
    Model,
    NodeRunObservation,
    PipelineMemory,
    Run,
)
from shared.services import init_services, shutdown_services

logger = logging.getLogger(__name__)

# Child-first so foreign keys to ``runs`` resolve on wipe.
_WIPE_TABLES = (
    "pipeline_memories",
    "node_run_observations",
    "artifacts",
    "simulation_observations",
    "models",
    "experiments",
    "runs",
)

_EMBED_BATCH = 64
_SCROLL_BATCH = 512
_VECTOR_COLLECTIONS = ("memories_dense", "memories_sparse")


# --------------------------------------------------------------------------- #
# JSON → ORM coercion helpers
# --------------------------------------------------------------------------- #
def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _uid(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


def _load(bundle: Path, name: str) -> list[dict]:
    path = bundle / "database" / name
    if not path.exists():
        logger.warning("restore: %s missing — skipping", name)
        return []
    return json.loads(path.read_text())


# --------------------------------------------------------------------------- #
# Postgres
# --------------------------------------------------------------------------- #
async def _wipe_postgres(services, *, dry_run: bool) -> None:
    if dry_run:
        logger.info("restore: would wipe PG tables %s", ", ".join(_WIPE_TABLES))
        return
    async with services.db.get_session() as session:
        for table_name in _WIPE_TABLES:
            await session.execute(text(f"DELETE FROM {table_name}"))
        await session.commit()
    logger.info("restore: wiped PG tables %s", ", ".join(_WIPE_TABLES))


def _build_rows(bundle: Path) -> list[list]:
    """Return rows grouped by FK-dependency level (runs first, children last)."""
    runs: list = []
    models: list = []
    children: list = []
    for row in _load(bundle, "runs.json"):
        runs.append(
            Run(
                id=_uid(row["id"]),
                created_at=_dt(row.get("created_at")),
                problem_description=row["problem_description"],
                status=row.get("status", "created"),
                kind=row.get("kind", "eval"),
                s3_report_key=row.get("s3_report_key"),
                s3_prefix=row["s3_prefix"],
                artifact_count=row.get("artifact_count"),
                final_stage=row.get("final_stage"),
                memory_results=row.get("memory_results"),
            )
        )
    for row in _load(bundle, "models.json"):
        models.append(
            Model(
                id=_uid(row["id"]),
                class_name=row["class_name"],
                paradigm=row["paradigm"],
                formulation=row["formulation"],
                description=row.get("description"),
                run_id=_uid(row.get("run_id")),
                s3_model_key=row["s3_model_key"],
                s3_test_key=row.get("s3_test_key"),
                registered_at=_dt(row.get("registered_at")),
                metadata_=row.get("metadata"),
            )
        )
    for row in _load(bundle, "artifacts.json"):
        children.append(
            Artifact(
                id=_uid(row["id"]),
                s3_key=row["s3_key"],
                artifact_type=row["artifact_type"],
                run_id=_uid(row.get("run_id")),
                experiment_id=_uid(row.get("experiment_id")),
                created_at=_dt(row.get("created_at")),
                size_bytes=row["size_bytes"],
                content_type=row["content_type"],
            )
        )
    for row in _load(bundle, "node_run_observations.json"):
        children.append(
            NodeRunObservation(
                id=_uid(row["id"]),
                label=row["label"],
                key_value=row["key_value"],
                run_id=_uid(row["run_id"]),
                observed_at=_dt(row.get("observed_at")),
            )
        )
    for row in _load(bundle, "pipeline_memories.json"):
        children.append(
            PipelineMemory(
                id=_uid(row["id"]),
                content=row["content"],
                content_hash=row.get("content_hash"),
                namespace=row["namespace"],
                memory_type=row["memory_type"],
                source_stage=row["source_stage"],
                run_id=_uid(row["run_id"]),
                created_at=_dt(row.get("created_at")),
                updated_at=_dt(row.get("updated_at")),
                last_accessed_at=_dt(row.get("last_accessed_at")),
                access_count=row.get("access_count", 0),
                importance=row["importance"],
                confidence=row["confidence"],
                corroborations=row.get("corroborations", 0),
                contradictions=row.get("contradictions", 0),
                valid_from=_dt(row.get("valid_from")),
                valid_to=_dt(row.get("valid_to")),
                superseded_by=_uid(row.get("superseded_by")),
                metadata_=row.get("metadata"),
            )
        )
    return [runs, models, children]


async def _restore_postgres(services, bundle: Path, *, dry_run: bool) -> None:
    groups = _build_rows(bundle)
    counts: dict[str, int] = {}
    for group in groups:
        for row in group:
            counts[type(row).__name__] = counts.get(type(row).__name__, 0) + 1
    summary = ", ".join(f"{n} {k}" for k, n in counts.items())
    if dry_run:
        logger.info("restore: would insert %s", summary)
        return
    # Insert level by level (runs → models → run-scoped children) with a flush
    # between levels so every runs.id FK resolves. pipeline_memories.superseded_by
    # is a self-FK within the last level — the unit of work orders those rows.
    async with services.db.get_session() as session:
        for group in groups:
            session.add_all(group)
            await session.flush()
        await session.commit()
    logger.info("restore: inserted %s", summary)


# --------------------------------------------------------------------------- #
# MinIO
# --------------------------------------------------------------------------- #
async def _wipe_minio(services, bundle: Path, *, dry_run: bool) -> None:
    prefixes = {p.name for p in (bundle / "storage").iterdir() if p.is_dir()}
    for prefix in sorted(prefixes):
        keys = await services.storage.list(f"{prefix}/")
        if dry_run:
            logger.info(
                "restore: would delete %d MinIO objects under %s/", len(keys), prefix
            )
            continue
        for key in keys:
            await services.storage.delete(key)
        logger.info("restore: deleted %d MinIO objects under %s/", len(keys), prefix)


async def _restore_minio(services, bundle: Path, *, dry_run: bool) -> None:
    storage_root = bundle / "storage"
    files = [p for p in storage_root.rglob("*") if p.is_file()]
    if dry_run:
        logger.info("restore: would upload %d files to MinIO", len(files))
        return
    uploaded = 0
    for path in files:
        key = path.relative_to(storage_root).as_posix()
        await services.storage.put(key, path.read_bytes())
        uploaded += 1
    logger.info("restore: uploaded %d files to MinIO", uploaded)


# --------------------------------------------------------------------------- #
# Neo4j
# --------------------------------------------------------------------------- #
async def _restore_neo4j(services, bundle: Path, *, dry_run: bool) -> None:
    snaps = sorted(bundle.glob("kg_snapshot_*.json"))
    if not snaps:
        logger.warning("restore: no kg_snapshot_*.json in bundle — skipping Neo4j")
        return
    snap = json.loads(snaps[-1].read_text())
    n_nodes, n_rels = len(snap.get("nodes", [])), len(snap.get("relations", []))
    if dry_run:
        logger.info(
            "restore: would restore %d nodes / %d relations to Neo4j", n_nodes, n_rels
        )
        return
    await kgadmin.restore(snap, services, reset_first=True)
    logger.info("restore: restored %d nodes / %d relations to Neo4j", n_nodes, n_rels)


# --------------------------------------------------------------------------- #
# Qdrant (re-embed from restored pipeline_memories)
# --------------------------------------------------------------------------- #
def _vector_payload(memory: PipelineMemory) -> dict:
    created = memory.created_at or datetime.now(UTC)
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    payload = {
        "entity_id": str(memory.id),
        "namespace": memory.namespace,
        "source_stage": memory.source_stage,
        "source_kind": "pipeline",
        "run_id": str(memory.run_id),
        "importance": memory.importance,
        "created_at": created.isoformat(),
        "text_preview": memory.content[:200],
    }
    if memory.content_hash:
        payload["content_hash"] = memory.content_hash
    return payload


async def _reindex_qdrant(services, *, dry_run: bool) -> None:
    from sqlalchemy import select

    from shared.knowledge_graph import KG_RELATION_NAMESPACE

    if services.embeddings is None or services.vectors is None:
        raise RuntimeError(
            "Qdrant re-index needs embeddings + vectors. Check VOYAGE_API_KEY "
            "and QDRANT_URL (loaded from phase2-juan/.env)."
        )

    async with services.db.get_session() as session:
        result = await session.execute(
            select(PipelineMemory)
            .where(PipelineMemory.valid_to.is_(None))
            .where(PipelineMemory.namespace != KG_RELATION_NAMESPACE)
            .order_by(PipelineMemory.created_at.asc())
        )
        memories = list(result.scalars().all())

    live_ids = {str(m.id) for m in memories}
    if dry_run:
        logger.info(
            "restore: would re-index %d live memories into Qdrant", len(memories)
        )
        return

    indexed = 0
    for start in range(0, len(memories), _EMBED_BATCH):
        batch = memories[start : start + _EMBED_BATCH]
        vectors = await services.embeddings.embed_texts([m.content for m in batch])
        for memory, vector in zip(batch, vectors, strict=True):
            payload = _vector_payload(memory)
            await services.vectors.upsert_dense(
                "memories_dense", str(memory.id), vector, payload
            )
            await services.vectors.upsert_sparse(
                "memories_sparse", str(memory.id), memory.content, payload
            )
            indexed += 1
    logger.info("restore: re-indexed %d memories into Qdrant", indexed)
    await _delete_qdrant_orphans(services, live_ids=live_ids)


async def _delete_qdrant_orphans(services, *, live_ids: set[str]) -> None:
    """Drop stale ``source_kind='pipeline'`` points not backed by a live memory."""
    client = services.vectors._c()
    for collection in _VECTOR_COLLECTIONS:
        deleted, offset = 0, None
        while True:
            points, offset = await client.scroll(
                collection_name=collection,
                limit=_SCROLL_BATCH,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            orphans = []
            for point in points:
                pid = str(point.id)
                payload = point.payload or {}
                if pid in live_ids or payload.get("source_kind") != "pipeline":
                    continue
                try:
                    uuid.UUID(pid)
                except ValueError:
                    continue
                orphans.append(pid)
            if orphans:
                await services.vectors.delete(collection, orphans)
                deleted += len(orphans)
            if offset is None:
                break
        if deleted:
            logger.info(
                "restore: deleted %d orphan points from %s", deleted, collection
            )


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
async def _main(bundle: Path, *, wipe: bool, dry_run: bool) -> None:
    manifest = json.loads((bundle / "manifest.json").read_text())
    logger.info(
        "restore: bundle suite=%s runs=%s%s",
        manifest.get("suite"),
        manifest.get("run_ids"),
        " [DRY-RUN]" if dry_run else "",
    )

    services = await init_services()
    try:
        if wipe:
            await _wipe_postgres(services, dry_run=dry_run)
            await _wipe_minio(services, bundle, dry_run=dry_run)
        await _restore_postgres(services, bundle, dry_run=dry_run)
        await _restore_minio(services, bundle, dry_run=dry_run)
        await _restore_neo4j(services, bundle, dry_run=dry_run)
        await _reindex_qdrant(services, dry_run=dry_run)
    finally:
        await shutdown_services(services)
    logger.info("restore: done")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "bundle", type=Path, help="Path to the artifact-bundle directory"
    )
    parser.add_argument(
        "--no-wipe",
        dest="wipe",
        action="store_false",
        help="Layer on top of existing data instead of wiping first",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no writes")
    parser.add_argument(
        "--env",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "phase2-juan" / ".env",
        help="dotenv with VOYAGE_API_KEY etc. (default: phase2-juan/.env)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    if args.env.exists():
        load_dotenv(args.env)
    bundle_dir = args.bundle.resolve()
    if not (bundle_dir / "manifest.json").exists():
        raise SystemExit(f"No manifest.json under {bundle_dir} — not a bundle dir")
    asyncio.run(_main(bundle_dir, wipe=args.wipe, dry_run=args.dry_run))

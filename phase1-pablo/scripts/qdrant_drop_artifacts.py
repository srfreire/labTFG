"""One-shot Qdrant cleanup: drop the collections retired by P4-002.

Removes ``artifacts_dense``, ``artifacts_sparse`` and
``kg_entities_dense`` from a populated Qdrant. After P4-002:

- ``artifacts_*`` are gone — raw stage output lives on MinIO and was
  never queried by the agent loop. The chunks were a write-only index.
- ``kg_entities_dense`` moved into Neo4j as a native vector index on
  ``n.embedding`` for slug-like labels. Run
  ``scripts/backfill_kg_entities.py`` first to populate the new index;
  this script then sweeps the now-orphaned Qdrant collection.

The script is destructive — back up the collections first if they hold
anything you might want to recover.

Usage:

    # Dry run — list what would be dropped
    uv run scripts/qdrant_drop_artifacts.py --dry-run

    # Apply
    uv run scripts/qdrant_drop_artifacts.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import shared

logger = logging.getLogger(__name__)


DROP_COLLECTIONS = (
    "artifacts_dense",
    "artifacts_sparse",
    "kg_entities_dense",
)


async def _drop(*, dry_run: bool) -> None:
    if shared.vectors is None:
        raise RuntimeError("shared.init() did not bring up the VectorStore")

    client = shared.vectors._c()
    existing = {c.name for c in (await client.get_collections()).collections}

    for name in DROP_COLLECTIONS:
        if name not in existing:
            logger.info("qdrant_drop_artifacts: %s — already absent", name)
            continue
        if dry_run:
            logger.info("qdrant_drop_artifacts: %s — would drop", name)
            continue
        await client.delete_collection(name)
        logger.info("qdrant_drop_artifacts: %s — dropped", name)


async def _main(*, dry_run: bool) -> None:
    await shared.init()
    try:
        await _drop(dry_run=dry_run)
    finally:
        await shared.shutdown()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the collections that would be dropped without mutating Qdrant.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    asyncio.run(_main(dry_run=args.dry_run))

"""One-shot cleanup: blank `confidence` payloads in `memories_dense` and
`memories_sparse`.

Pre-P3-002 every memory point carried a stale `confidence` field that
drifted away from the Postgres value (only `memories_dense` was synced
on decay, sparse never was). After P3-002 the field is no longer
written and retrieval ignores it, but old points still hold stale
values. This script blanks them in-place.

Idempotent — re-running on a populated DB does no harm; the
`set_payload` call is a no-op when the field is already None.

Usage:

    # Dry run — count points without mutating
    uv run scripts/qdrant_strip_confidence.py --dry-run

    # Apply
    uv run scripts/qdrant_strip_confidence.py

Not auto-run by anything; invoke manually after deploying P3-002.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from shared.services import init_services, shutdown_services

logger = logging.getLogger(__name__)


COLLECTIONS = ("memories_dense", "memories_sparse")
SCROLL_BATCH = 1024


async def _strip_collection(
    collection: str, *, dry_run: bool, services
) -> tuple[int, int]:
    """Walk every point in *collection* and blank `confidence`.

    Returns (points_seen, points_updated). Points already missing
    `confidence` (or holding `None`) are skipped to keep the run cheap on
    a re-execution.
    """
    if services.vectors is None:
        raise RuntimeError("init_services() did not bring up the VectorStore")

    client = services.vectors._c()
    seen = 0
    updated = 0
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

        stale_ids = [
            p.id
            for p in points
            if p.payload is not None and p.payload.get("confidence") is not None
        ]
        seen += len(points)

        if stale_ids and not dry_run:
            await client.set_payload(
                collection_name=collection,
                payload={"confidence": None},
                points=stale_ids,
            )
        updated += len(stale_ids)

        if offset is None:
            break

    return seen, updated


async def _main(*, dry_run: bool) -> None:
    services = await init_services()
    try:
        for collection in COLLECTIONS:
            seen, updated = await _strip_collection(
                collection, dry_run=dry_run, services=services
            )
            verb = "would blank" if dry_run else "blanked"
            logger.info(
                "qdrant_strip_confidence: %s — scanned %d, %s %d stale `confidence`",
                collection,
                seen,
                verb,
                updated,
            )
    finally:
        await shutdown_services(services)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count stale `confidence` payloads without mutating Qdrant.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    asyncio.run(_main(dry_run=args.dry_run))

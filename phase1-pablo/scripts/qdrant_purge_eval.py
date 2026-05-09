"""Idempotent Qdrant purge for deleted eval runs (memory-refactor P3-003).

Two-step retention lifecycle::

    uv run cli_eval prune --older-than 30d \
        | uv run scripts/qdrant_purge_eval.py

Step 1 (``cli_eval prune``) deletes ``kind='eval'`` runs from Postgres,
cascading to ``memories``, ``artifacts`` and ``node_run_observations``
via FK ``ON DELETE CASCADE``. Step 2 (this script) reads the run_ids
from stdin and deletes the matching points from each Qdrant collection
that carries ``run_id`` in its payload.

Idempotent: deleting a run_id whose points are already gone is a no-op,
so safely re-runnable after a partial pipeline failure.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid

import typer

from shared.services import init_services, shutdown_services

logger = logging.getLogger(__name__)

# Collections whose payloads carry ``run_id`` (see docs/memory-system.md §4.1).
# After P4-002 only ``memories_*`` survive — ``artifacts_*`` and
# ``kg_entities_dense`` were dropped.
PURGE_COLLECTIONS = (
    "memories_dense",
    "memories_sparse",
)


app = typer.Typer(no_args_is_help=False, add_completion=False)


def _parse_input(raw: str) -> list[str]:
    """Parse run_ids from JSON (the ``cli_eval prune`` shape) or one-per-line.

    Accepts:
      * ``{"run_ids": ["uuid", ...], ...}`` — full prune output (preferred).
      * ``["uuid", ...]`` — bare list.
      * Plain text, one UUID per line.

    Validates each id is a UUID early so a malformed pipe surfaces as a
    parse error instead of silently matching zero Qdrant points.
    """
    raw = raw.strip()
    if not raw:
        return []
    if raw[0] in "{[":
        data = json.loads(raw)
        ids = data["run_ids"] if isinstance(data, dict) else data
    else:
        ids = [line.strip() for line in raw.splitlines() if line.strip()]
    return [str(uuid.UUID(i)) for i in ids]


@app.command()
def purge(
    run_ids_csv: str = typer.Option(
        "",
        "--run-ids",
        help="Comma-separated UUIDs (overrides stdin).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print what would be deleted without modifying Qdrant.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Purge Qdrant points whose payload ``run_id`` matches input run_ids."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

    if run_ids_csv:
        try:
            run_ids = [
                str(uuid.UUID(s.strip())) for s in run_ids_csv.split(",") if s.strip()
            ]
        except ValueError as exc:
            typer.echo(f"Invalid UUID in --run-ids: {exc}", err=True)
            raise typer.Exit(code=2) from exc
    else:
        try:
            run_ids = _parse_input(sys.stdin.read())
        except (json.JSONDecodeError, ValueError) as exc:
            typer.echo(f"Could not parse run_ids from stdin: {exc}", err=True)
            raise typer.Exit(code=2) from exc

    if not run_ids:
        typer.echo(json.dumps({"run_ids": [], "collections": {}, "dry_run": dry_run}))
        return

    asyncio.run(_run(run_ids, dry_run=dry_run))


async def _run(run_ids: list[str], *, dry_run: bool) -> None:
    services = await init_services()
    try:
        result = await _purge(run_ids, dry_run=dry_run, services=services)
    finally:
        await shutdown_services(services)
    typer.echo(json.dumps(result))


async def _purge(run_ids: list[str], *, dry_run: bool, services) -> dict:
    if services.vectors is None:
        raise RuntimeError("services.vectors is None — Qdrant not initialised")

    per_collection: dict[str, int] = {}
    for collection in PURGE_COLLECTIONS:
        if dry_run:
            per_collection[collection] = 0
            logger.info(
                "[dry-run] would delete points in %s for %d run_id(s)",
                collection,
                len(run_ids),
            )
            continue
        dispatched = await services.vectors.delete_by_run_ids(collection, run_ids)
        per_collection[collection] = dispatched
        logger.info("purged %s for %d run_id(s)", collection, dispatched)

    return {
        "run_ids": run_ids,
        "collections": per_collection,
        "dry_run": dry_run,
    }


if __name__ == "__main__":
    app()

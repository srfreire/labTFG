"""Monthly rollup of old Reflection nodes (memory-refactor P3-003).

Walks Neo4j for ``Reflection`` nodes whose ``created_at`` is older than
``--older-than-days`` (default 90), groups them by month-cohort, summarises
each cohort into a single ``RollupReflection`` node keyed by ``rollup:YYYY-MM``,
and detach-deletes the originals.

Idempotent. The merge:
- Creates the ``RollupReflection`` node if absent.
- Otherwise, appends only the source IDs not already in the rollup
  (defends against partial-failure replays where the prior delete
  did not commit but the merge did).

Each cohort's merge + delete runs in a single managed transaction —
both writes succeed together or both fail together.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import typer

from shared.services import init_services, shutdown_services

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=False, add_completion=False)

DEFAULT_RETENTION_DAYS = 90


@app.command()
def rollup(
    older_than_days: int = typer.Option(
        DEFAULT_RETENTION_DAYS,
        "--older-than-days",
        help="Roll up Reflections whose created_at is older than this.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print cohorts without modifying Neo4j."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Roll up old Reflection nodes into monthly RollupReflection summaries."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    if older_than_days <= 0:
        typer.echo("--older-than-days must be > 0", err=True)
        raise typer.Exit(code=2)
    asyncio.run(_run(older_than_days, dry_run=dry_run))


async def _run(older_than_days: int, *, dry_run: bool) -> None:
    services = await init_services()
    try:
        result = await _rollup(older_than_days, dry_run=dry_run, services=services)
    finally:
        await shutdown_services(services)
    typer.echo(json.dumps(result, indent=2))


def _month_cohort(created_at: str | None) -> str | None:
    """Extract a ``YYYY-MM`` cohort key from an ISO datetime string."""
    if not created_at or len(created_at) < 7:
        return None
    return created_at[:7]


async def _rollup(older_than_days: int, *, dry_run: bool, services) -> dict:
    if services.kg is None:
        raise RuntimeError("services.kg is None — Neo4j not initialised")

    cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()

    rows = await services.kg.query(
        "MATCH (r:Reflection) "
        "WHERE r.created_at IS NOT NULL AND r.created_at < $cutoff "
        "RETURN r.id AS id, r.created_at AS created_at",
        {"cutoff": cutoff},
    )

    cohorts: dict[str, list[str]] = {}
    skipped_no_date = 0
    for row in rows:
        month = _month_cohort(row["created_at"])
        if month is None:
            skipped_no_date += 1
            continue
        cohorts.setdefault(month, []).append(row["id"])

    summary: dict[str, dict] = {}
    now_iso = datetime.now(UTC).isoformat()

    for month, ids in sorted(cohorts.items()):
        rollup_id = f"rollup:{month}"
        if dry_run:
            summary[month] = {
                "rollup_id": rollup_id,
                "candidates": len(ids),
                "merged": 0,
            }
            continue
        merged = await _merge_and_delete(
            rollup_id, month, ids, now_iso, services=services
        )
        summary[month] = {
            "rollup_id": rollup_id,
            "candidates": len(ids),
            "merged": merged,
        }

    return {
        "older_than_days": older_than_days,
        "cutoff": cutoff,
        "dry_run": dry_run,
        "skipped_no_date": skipped_no_date,
        "cohorts": summary,
        "total_merged": sum(c["merged"] for c in summary.values()),
    }


async def _merge_and_delete(
    rollup_id: str, month: str, ids: list[str], now_iso: str, *, services
) -> int:
    """Atomically MERGE the rollup and DETACH DELETE the original Reflections.

    Returns the number of *new* source IDs appended to the rollup. IDs already
    present (from a partial prior run) are deduped server-side and counted
    as zero new merges.
    """
    assert services.kg is not None

    async def _work(tx):
        # Single SET path so the CREATE and MATCH branches share dedup logic
        # and the returned ``merged`` count is consistent in both cases.
        merge_result = await tx.run(
            "MERGE (rr:RollupReflection {id: $rollup_id}) "
            "ON CREATE SET rr.month = $month, "
            "    rr.created_at = $now, "
            "    rr.source_reflection_ids = [] "
            "WITH rr, "
            "    [id IN $ids WHERE NOT id IN coalesce(rr.source_reflection_ids, [])] "
            "    AS new_ids "
            "SET rr.source_reflection_ids = "
            "        coalesce(rr.source_reflection_ids, []) + new_ids, "
            "    rr.count = coalesce(rr.count, 0) + size(new_ids), "
            "    rr.last_rolled_up_at = $now "
            "RETURN size(new_ids) AS merged",
            {"rollup_id": rollup_id, "month": month, "ids": ids, "now": now_iso},
        )
        record = await merge_result.single()
        merged = int(record["merged"]) if record else 0

        await tx.run(
            "MATCH (r:Reflection) WHERE r.id IN $ids DETACH DELETE r",
            {"ids": ids},
        )
        return merged

    return await services.kg.execute_write(_work)


if __name__ == "__main__":
    app()

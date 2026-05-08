"""add node_run_observations table and backfill from KG

Replaces the unbounded ``n.run_ids`` array on Neo4j nodes with cheap
``run_count`` / ``last_run_at`` properties on the graph plus a Postgres
``node_run_observations`` table for per-run provenance. See
``docs/specs/memory-refactor/phase-0-stop-lying.md`` (R4) and
``docs/memory-system.md`` §A10.

The Neo4j-side backfill walks every node carrying a ``run_ids`` array,
sets ``run_count = size(run_ids)`` and ``last_run_at = updated_at``, and
records each array element as one Postgres row (best-effort: a missing
``runs`` row for a given run_id silently drops that observation rather
than aborting the migration). The ``run_ids`` property itself is kept
in place for one release cycle — a follow-up alembic step (P3 cleanup,
TODO below) drops it once callers stop reading.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5f8a92b1c4e"
down_revision: str | None = "c7a95bfd1552"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    op.create_table(
        "node_run_observations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=40), nullable=False),
        sa.Column("key_value", sa.String(length=120), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "label", "key_value", "run_id", name="uq_node_run_observations_node_run"
        ),
    )
    op.create_index(
        "ix_node_run_observations_run_id",
        "node_run_observations",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_node_run_observations_node",
        "node_run_observations",
        ["label", "key_value"],
        unique=False,
    )

    _backfill_from_kg()

    # TODO(P3 cleanup): once every reader of `n.run_ids` has been migrated to
    # `run_count` / `last_run_at` / node_run_observations, ship a follow-up
    # alembic revision that runs `MATCH (n) WHERE n.run_ids IS NOT NULL
    # REMOVE n.run_ids` against Neo4j.


def downgrade() -> None:
    op.drop_index("ix_node_run_observations_node", table_name="node_run_observations")
    op.drop_index("ix_node_run_observations_run_id", table_name="node_run_observations")
    op.drop_table("node_run_observations")


# ---------------------------------------------------------------------------
# Idempotent KG-side backfill
# ---------------------------------------------------------------------------


def _backfill_from_kg() -> None:
    """Convert legacy ``n.run_ids`` arrays into ``run_count`` / ``last_run_at``
    + Postgres rows. Skipped silently if Neo4j credentials are absent.

    Idempotent: on re-run, nodes already carrying ``run_count`` are recomputed
    from whatever ``run_ids`` still exists, and the UNIQUE
    ``(label, key_value, run_id)`` constraint absorbs duplicate inserts.
    """
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    if not (uri and user and password):
        logger.warning(
            "node_run_observations backfill skipped — NEO4J_URI/USER/PASSWORD "
            "not set; Neo4j-side migration must be run separately"
        )
        return

    try:
        from neo4j import GraphDatabase
    except ImportError:
        logger.warning(
            "node_run_observations backfill skipped — neo4j driver not installed"
        )
        return

    bind = op.get_bind()
    valid_run_ids = {
        row[0] for row in bind.execute(sa.text("SELECT id FROM runs")).fetchall()
    }

    insert_attempts = 0
    nodes_touched = 0
    skipped_missing_run = 0

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            nodes = session.run(
                "MATCH (n) WHERE n.run_ids IS NOT NULL "
                "RETURN labels(n) AS labels, properties(n) AS props, "
                "elementId(n) AS eid"
            ).data()

            for node in nodes:
                labels = node.get("labels") or []
                if not labels:
                    continue
                label = labels[0]
                props = node.get("props") or {}
                run_ids = props.get("run_ids") or []
                if not run_ids:
                    continue

                key_value = _extract_key_value(props)
                if key_value is None:
                    continue
                # Postgres column cap.
                key_value = str(key_value)[:120]

                last_run_at = props.get("updated_at") or props.get("created_at")

                session.run(
                    "MATCH (n) WHERE elementId(n) = $eid "
                    "SET n.run_count = $count, n.last_run_at = $last_at",
                    eid=node["eid"],
                    count=len(run_ids),
                    last_at=last_run_at,
                )
                nodes_touched += 1

                for raw_run_id in run_ids:
                    parsed = _parse_uuid(raw_run_id)
                    if parsed is None or parsed not in valid_run_ids:
                        skipped_missing_run += 1
                        continue
                    bind.execute(
                        sa.text(
                            "INSERT INTO node_run_observations "
                            "(id, label, key_value, run_id, observed_at) "
                            "VALUES (:id, :label, :key_value, :run_id, "
                            "COALESCE(:observed_at, now())) "
                            "ON CONFLICT (label, key_value, run_id) DO NOTHING"
                        ),
                        {
                            "id": uuid.uuid4(),
                            "label": label[:40],
                            "key_value": key_value,
                            "run_id": parsed,
                            "observed_at": last_run_at,
                        },
                    )
                    insert_attempts += 1
    finally:
        driver.close()

    # `insert_attempts` counts the rows we asked Postgres to insert; the
    # ON CONFLICT clause may have skipped some on a re-run, so this is an
    # upper bound, not the literal row delta.
    logger.info(
        "node_run_observations backfill: nodes_touched=%d insert_attempts=%d "
        "skipped_missing_run=%d",
        nodes_touched,
        insert_attempts,
        skipped_missing_run,
    )


def _extract_key_value(props: dict) -> str | None:
    """Pick the same natural-key surface as ``kg_writer._resolve_natural_key``.

    Order matches `_FALLBACK_KEY_NAMES` in kg_writer plus the synthetic id
    written by the populate_kg fallback.
    """
    for candidate in ("slug", "id", "doi", "url", "name", "title", "_synthetic_id"):
        val = props.get(candidate)
        if val:
            return str(val)
    return None


def _parse_uuid(raw: object) -> uuid.UUID | None:
    if isinstance(raw, uuid.UUID):
        return raw
    if isinstance(raw, str):
        try:
            return uuid.UUID(raw)
        except ValueError:
            return None
    return None

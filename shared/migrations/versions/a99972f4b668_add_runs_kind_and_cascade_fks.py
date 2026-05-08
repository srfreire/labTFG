"""add runs.kind and cascade FKs from runs to dependents

Adds a ``kind ∈ {prod, eval}`` column on ``runs`` so the eval driver can
tag its inserts and the new ``cli_eval prune`` command can reap them by
age. Also strengthens the existing FKs from ``memories.run_id``,
``node_run_observations.run_id``, and ``artifacts.run_id`` to ``ON
DELETE CASCADE`` so deleting an eval run cleans up its descendants in a
single SQL statement (memory-refactor P3-003 / phase-3 R3).

Revision ID: a99972f4b668
Revises: d5f8a92b1c4e
Create Date: 2026-05-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a99972f4b668"
down_revision: str | None = "d5f8a92b1c4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Each tuple: (table, fk_constraint_name, local_col, ref_table, ref_col).
_CASCADE_FKS: tuple[tuple[str, str, str, str, str], ...] = (
    ("memories", "memories_run_id_fkey", "run_id", "runs", "id"),
    (
        "node_run_observations",
        "node_run_observations_run_id_fkey",
        "run_id",
        "runs",
        "id",
    ),
    ("artifacts", "artifacts_run_id_fkey", "run_id", "runs", "id"),
)


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "kind",
            sa.String(length=10),
            nullable=False,
            server_default=sa.text("'prod'"),
        ),
    )
    op.create_check_constraint(
        "runs_kind_check",
        "runs",
        "kind IN ('prod', 'eval')",
    )

    for table, name, local, ref_table, ref_col in _CASCADE_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name,
            table,
            ref_table,
            [local],
            [ref_col],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table, name, local, ref_table, ref_col in _CASCADE_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name,
            table,
            ref_table,
            [local],
            [ref_col],
        )

    op.drop_constraint("runs_kind_check", "runs", type_="check")
    op.drop_column("runs", "kind")

"""add pipeline memory content hash

Revision ID: f3b2c1d4e5a6
Revises: e271a24ca95c
Create Date: 2026-06-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3b2c1d4e5a6"
down_revision: str | None = "e271a24ca95c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pipeline_memories",
        sa.Column("content_hash", sa.String(length=32), nullable=True),
    )
    op.execute(
        """
        UPDATE pipeline_memories
        SET content_hash = md5(
            lower(regexp_replace(btrim(content), '[[:space:]]+', ' ', 'g'))
        )
        WHERE content_hash IS NULL
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                first_value(id) OVER (
                    PARTITION BY run_id, source_stage, namespace, memory_type, content_hash
                    ORDER BY created_at ASC, id ASC
                ) AS survivor_id,
                row_number() OVER (
                    PARTITION BY run_id, source_stage, namespace, memory_type, content_hash
                    ORDER BY created_at ASC, id ASC
                ) AS rn
            FROM pipeline_memories
            WHERE valid_to IS NULL
              AND content_hash IS NOT NULL
        )
        UPDATE pipeline_memories AS pm
        SET valid_to = now(), superseded_by = ranked.survivor_id
        FROM ranked
        WHERE pm.id = ranked.id
          AND ranked.rn > 1
        """
    )
    op.create_index(
        "ix_pipeline_memories_content_hash",
        "pipeline_memories",
        ["content_hash"],
    )
    op.create_index(
        "uq_pipeline_memories_live_fact_key",
        "pipeline_memories",
        ["run_id", "source_stage", "namespace", "memory_type", "content_hash"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND content_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_pipeline_memories_live_fact_key", table_name="pipeline_memories")
    op.drop_index("ix_pipeline_memories_content_hash", table_name="pipeline_memories")
    op.drop_column("pipeline_memories", "content_hash")

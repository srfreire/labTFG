"""models: UUID PK + paradigm/formulation slug columns

Revision ID: a1b2c3d4e5f6
Revises: e8157a385508
Create Date: 2026-04-14 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e8157a385508"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new UUID id column
    op.add_column("models", sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")))
    # Add formulation slug column
    op.add_column("models", sa.Column("formulation", sa.String(length=255), nullable=False, server_default=sa.text("''")))

    # Make paradigm NOT NULL (backfill NULLs first)
    op.execute("UPDATE models SET paradigm = '' WHERE paradigm IS NULL")
    op.alter_column("models", "paradigm", nullable=False)

    # Remove server defaults now that existing rows are handled
    op.alter_column("models", "id", server_default=None)
    op.alter_column("models", "formulation", server_default=None)

    # Drop old PK and column
    op.drop_constraint("models_pkey", "models", type_="primary")
    op.drop_column("models", "formulation_id")

    # Create new PK on id
    op.create_primary_key("models_pkey", "models", ["id"])

    # Add unique constraint
    op.create_unique_constraint(
        "uq_models_run_paradigm_formulation",
        "models",
        ["run_id", "paradigm", "formulation"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_models_run_paradigm_formulation", "models", type_="unique")
    op.drop_constraint("models_pkey", "models", type_="primary")
    op.add_column("models", sa.Column("formulation_id", sa.String(length=255), nullable=False, server_default=sa.text("''")))
    op.alter_column("models", "formulation_id", server_default=None)
    op.create_primary_key("models_pkey", "models", ["formulation_id"])
    op.alter_column("models", "paradigm", nullable=True)
    op.drop_column("models", "formulation")
    op.drop_column("models", "id")

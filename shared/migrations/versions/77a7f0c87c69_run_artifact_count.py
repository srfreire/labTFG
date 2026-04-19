"""run_artifact_count

Revision ID: 77a7f0c87c69
Revises: a1b2c3d4e5f6
Create Date: 2026-04-19 18:03:04.744716
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '77a7f0c87c69'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("artifact_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runs", "artifact_count")

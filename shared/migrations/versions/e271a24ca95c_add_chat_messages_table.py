"""add chat_messages table

Revision ID: e271a24ca95c
Revises: e7a4c9d2b813
Create Date: 2026-05-11 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e271a24ca95c"
down_revision: str | None = "e7a4c9d2b813"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("experiment_id", sa.UUID(), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_messages_session", "chat_messages", ["session_id"], unique=False
    )
    op.create_index(
        "ix_chat_messages_experiment",
        "chat_messages",
        ["experiment_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_messages_created", "chat_messages", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_created", table_name="chat_messages")
    op.drop_index("ix_chat_messages_experiment", table_name="chat_messages")
    op.drop_index("ix_chat_messages_session", table_name="chat_messages")
    op.drop_table("chat_messages")

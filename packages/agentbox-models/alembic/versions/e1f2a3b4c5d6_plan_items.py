"""plan items

Revision ID: e1f2a3b4c5d6
Revises: c4f8e2a1b9d3
Create Date: 2026-11-19 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "c4f8e2a1b9d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planitem",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("sessionrow.id"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_planitem_session_id", "planitem", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_planitem_session_id", table_name="planitem")
    op.drop_table("planitem")

"""sub-agent sessions

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-20 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessionrow",
        sa.Column(
            "parent_session_id",
            sa.String(),
            sa.ForeignKey("sessionrow.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sessionrow_parent_session_id", "sessionrow", ["parent_session_id"]
    )
    op.add_column("sessionrow", sa.Column("sub_session_status", sa.String(), nullable=True))
    op.add_column("sessionrow", sa.Column("sub_session_error", sa.String(), nullable=True))
    op.add_column("sessionrow", sa.Column("sub_session_output", sa.String(), nullable=True))
    op.add_column(
        "sessionrow",
        sa.Column("sub_session_depth", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("sessionrow", "sub_session_depth")
    op.drop_column("sessionrow", "sub_session_output")
    op.drop_column("sessionrow", "sub_session_error")
    op.drop_column("sessionrow", "sub_session_status")
    op.drop_index("ix_sessionrow_parent_session_id", table_name="sessionrow")
    op.drop_column("sessionrow", "parent_session_id")

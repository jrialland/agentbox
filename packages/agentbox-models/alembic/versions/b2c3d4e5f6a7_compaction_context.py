"""compaction context fields

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-20 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("model", sa.Column("context_window", sa.Integer(), nullable=True))
    op.add_column("turnrow", sa.Column("context_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("turnrow", "context_tokens")
    op.drop_column("model", "context_window")

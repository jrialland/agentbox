"""agent avatar

Revision ID: 7a1c2f3d4e5b
Revises: 518db7d88349
Create Date: 2026-11-19 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a1c2f3d4e5b"
down_revision: str | Sequence[str] | None = "518db7d88349"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent", sa.Column("avatar_data", sa.LargeBinary(), nullable=True))
    op.add_column("agent", sa.Column("avatar_media_type", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent", "avatar_media_type")
    op.drop_column("agent", "avatar_data")

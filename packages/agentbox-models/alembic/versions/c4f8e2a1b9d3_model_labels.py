"""model labels

Revision ID: c4f8e2a1b9d3
Revises: 7a1c2f3d4e5b
Create Date: 2026-11-19 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4f8e2a1b9d3"
down_revision: str | Sequence[str] | None = "7a1c2f3d4e5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "label",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
    )
    op.create_index("ix_label_name", "label", ["name"], unique=True)
    op.create_table(
        "modellabellink",
        sa.Column("model_id", sa.String(), sa.ForeignKey("model.id"), primary_key=True),
        sa.Column("label_id", sa.String(), sa.ForeignKey("label.id"), primary_key=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("agent", sa.Column("model_label", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent", "model_label")
    op.drop_table("modellabellink")
    op.drop_index("ix_label_name", table_name="label")
    op.drop_table("label")

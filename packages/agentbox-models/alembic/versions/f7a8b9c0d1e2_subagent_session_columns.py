"""subagent session columns

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
Create Date: 2026-11-22 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessionrow") as batch:
        batch.alter_column(
            "sub_session_status",
            new_column_name="subagent_session_status",
            existing_type=sa.String(),
        )
        batch.alter_column(
            "sub_session_error",
            new_column_name="subagent_session_error",
            existing_type=sa.String(),
        )
        batch.alter_column(
            "sub_session_output",
            new_column_name="subagent_session_output",
            existing_type=sa.String(),
        )
        batch.alter_column(
            "sub_session_depth",
            new_column_name="subagent_session_depth",
            existing_type=sa.Integer(),
        )
    with op.batch_alter_table("agent") as batch:
        batch.drop_column("sub_agent_ids")


def downgrade() -> None:
    with op.batch_alter_table("agent") as batch:
        batch.add_column(
            sa.Column(
                "sub_agent_ids",
                sa.String(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
    with op.batch_alter_table("sessionrow") as batch:
        batch.alter_column(
            "subagent_session_status",
            new_column_name="sub_session_status",
            existing_type=sa.String(),
        )
        batch.alter_column(
            "subagent_session_error",
            new_column_name="sub_session_error",
            existing_type=sa.String(),
        )
        batch.alter_column(
            "subagent_session_output",
            new_column_name="sub_session_output",
            existing_type=sa.String(),
        )
        batch.alter_column(
            "subagent_session_depth",
            new_column_name="sub_session_depth",
            existing_type=sa.Integer(),
        )

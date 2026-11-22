"""plugin state and permissions

Revision ID: f1a2b3c4d5e6
Revises: cb4176fc9480
Create Date: 2026-11-22 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
import sqlmodel.sql.sqltypes  # noqa: F401
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "cb4176fc9480"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERMISSIONS = (
    ("plugins_read", "plugins:read", "Read plugins"),
    ("plugins_write", "plugins:write", "Manage plugins"),
)


def upgrade() -> None:
    op.create_table(
        "pluginstate",
        sa.Column("id", sa.String(length=160), nullable=False),
        sa.Column("plugin_name", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False
        ),
        sa.Column(
            "updated_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pluginstate_project_id"),
        "pluginstate",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "agent_plugin_mcp_binding",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("agent_id", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("plugin", sa.String(length=64), nullable=False),
        sa.Column("server", sa.String(length=255), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=True),
        sa.Column("binding_id", sa.String(length=160), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agent.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_id",
            "position",
            name="uq_agent_plugin_mcp_pos",
        ),
    )
    op.create_index(
        op.f("ix_agent_plugin_mcp_binding_agent_id"),
        "agent_plugin_mcp_binding",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_plugin_mcp_binding_project_id"),
        "agent_plugin_mcp_binding",
        ["project_id"],
        unique=False,
    )

    bind = op.get_bind()
    for permission_id, name, description in _PERMISSIONS:
        existing_id = bind.execute(
            sa.text("SELECT id FROM permission WHERE name = :name"),
            {"name": name},
        ).scalar()
        effective_id = existing_id or permission_id
        if existing_id is None:
            bind.execute(
                sa.text(
                    "INSERT INTO permission (id, name, description) "
                    "VALUES (:id, :name, :description)"
                ),
                {
                    "id": permission_id,
                    "name": name,
                    "description": description,
                },
            )
        admin_id = bind.execute(
            sa.text("SELECT id FROM role WHERE name = 'admin'")
        ).scalar()
        if admin_id is None:
            continue
        linked = bind.execute(
            sa.text(
                "SELECT 1 FROM rolepermissionlink "
                "WHERE role_id = :role_id AND permission_id = :permission_id"
            ),
            {"role_id": admin_id, "permission_id": effective_id},
        ).first()
        if linked is None:
            bind.execute(
                sa.text(
                    "INSERT INTO rolepermissionlink (role_id, permission_id) "
                    "VALUES (:role_id, :permission_id)"
                ),
                {"role_id": admin_id, "permission_id": effective_id},
            )


def downgrade() -> None:
    bind = op.get_bind()
    permission_ids = [permission_id for permission_id, _, _ in _PERMISSIONS]
    for permission_id in permission_ids:
        bind.execute(
            sa.text(
                "DELETE FROM rolepermissionlink WHERE permission_id = :id"
            ),
            {"id": permission_id},
        )
        bind.execute(
            sa.text("DELETE FROM permission WHERE id = :id"),
            {"id": permission_id},
        )
    op.drop_table("agent_plugin_mcp_binding")
    op.drop_table("pluginstate")

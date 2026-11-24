"""Authentication and authorization tables.

This module owns users, roles, permissions, and API keys. Join tables use
``ON DELETE CASCADE`` so deleting a parent row also removes its memberships and
scopes. Timestamps are stored as timezone-aware UTC values.
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlmodel import Field, SQLModel
from sqlmodel.sql.sqltypes import UTCDateTime


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Columns use ``UTCDateTime``, which binds values as UTC and re-attaches the
    UTC offset on read when a backend returns a naive datetime (SQLite and MySQL
    lack a native timezone-aware type), keeping timestamps comparable.
    """
    return datetime.now(UTC)


class User(SQLModel, table=True):
    """An authenticated account and its password hash."""

    id: str = Field(sa_column=Column(String(32), primary_key=True))
    username: str = Field(sa_column=Column(String(255), nullable=False))
    email: str = Field(sa_column=Column(String(255), nullable=False))
    password_hash: str = Field(sa_column=Column(String(255), nullable=False))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class Role(SQLModel, table=True):
    """A named collection of permissions that can be assigned to users."""

    id: str = Field(sa_column=Column(String(32), primary_key=True))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    description: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )


class Permission(SQLModel, table=True):
    """A single capability that roles grant to users."""

    id: str = Field(sa_column=Column(String(32), primary_key=True))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    description: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )


class RolePermissionLink(SQLModel, table=True):
    """Association row granting a permission to a role."""

    # Composite primary key; both foreign keys cascade so a deleted role or
    # permission cannot leave a dangling grant behind.
    role_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
        )
    )
    permission_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("permission.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )


class UserRoleLink(SQLModel, table=True):
    """Association row assigning a role to a user."""

    # Composite primary key; cascading deletes keep role membership consistent
    # when either the user or the role is removed.
    user_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
        )
    )
    role_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
        )
    )


class ApiKey(SQLModel, table=True):
    """A hashed API key issued to a user for programmatic access.

    Attributes:
        key_hash: Only the hash is persisted; the plaintext key is never stored.
        expires_at: Optional UTC expiry; ``None`` means the key does not expire.
        revoked_at: Optional UTC revocation time; a non-null value disables the
            key before its expiry.
    """

    id: str = Field(sa_column=Column(String(32), primary_key=True))
    # Indexed for "keys belonging to this user" lookups; cascade removes the
    # keys when their owner is deleted.
    user_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    key_hash: str = Field(sa_column=Column(String(128), nullable=False))
    expires_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime, nullable=True)
    )
    revoked_at: datetime | None = Field(
        default=None, sa_column=Column(UTCDateTime, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class ApiKeyScope(SQLModel, table=True):
    """A single scope string granted to an API key."""

    # Explicit table name avoids driver-dependent default naming for the
    # composite-key scope table; scopes cascade with their parent key.
    __tablename__ = "apikey_scope"
    api_key_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("apikey.id", ondelete="CASCADE"), primary_key=True
        )
    )
    scope: str = Field(sa_column=Column(String(255), primary_key=True))

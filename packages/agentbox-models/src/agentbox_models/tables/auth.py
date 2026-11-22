from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlmodel import Field, SQLModel
from sqlmodel.sql.sqltypes import UTCDateTime


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    username: str = Field(sa_column=Column(String(255), nullable=False))
    email: str = Field(sa_column=Column(String(255), nullable=False))
    password_hash: str = Field(sa_column=Column(String(255), nullable=False))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class Role(SQLModel, table=True):
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    description: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )


class Permission(SQLModel, table=True):
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    description: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )


class RolePermissionLink(SQLModel, table=True):
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
    id: str = Field(sa_column=Column(String(32), primary_key=True))
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
    __tablename__ = "apikey_scope"
    api_key_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("apikey.id", ondelete="CASCADE"), primary_key=True
        )
    )
    scope: str = Field(sa_column=Column(String(255), primary_key=True))

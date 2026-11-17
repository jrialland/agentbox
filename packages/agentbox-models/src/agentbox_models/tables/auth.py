from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: str = Field(primary_key=True)
    username: str
    email: str
    password_hash: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class Role(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str | None = None


class Permission(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str | None = None


class RolePermissionLink(SQLModel, table=True):
    role_id: str = Field(primary_key=True, foreign_key="role.id")
    permission_id: str = Field(primary_key=True, foreign_key="permission.id")


class UserRoleLink(SQLModel, table=True):
    user_id: str = Field(primary_key=True, foreign_key="user.id")
    role_id: str = Field(primary_key=True, foreign_key="role.id")


class ApiKey(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    key_hash: str
    scopes: str = "[]"
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)

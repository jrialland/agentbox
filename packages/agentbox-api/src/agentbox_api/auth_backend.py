from datetime import UTC, datetime

import jwt
from sqlmodel import select
from starlette.authentication import AuthCredentials, AuthenticationBackend, BaseUser

from agentbox_api.config import Settings
from agentbox_api.security import decode_jwt, hash_api_key
from agentbox_models.repos.api_key_scopes import load_scopes
from agentbox_models.tables.auth import (
    ApiKey,
    Permission,
    RolePermissionLink,
    User,
    UserRoleLink,
)


class CurrentUser(BaseUser):
    def __init__(self, id: str, username: str, permissions: set[str]):
        self.id = id
        self.username = username
        self.permissions = permissions

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def display_name(self) -> str:
        return self.username

    @property
    def identity(self) -> str:
        return self.id


async def load_user_permissions(session, user_id: str) -> set[str]:
    role_ids = (
        await session.execute(select(UserRoleLink.role_id).where(UserRoleLink.user_id == user_id))
    ).scalars().all()
    if not role_ids:
        return set()
    perm_ids = (
        await session.execute(
            select(RolePermissionLink.permission_id).where(
                RolePermissionLink.role_id.in_(role_ids)  # ty: ignore[missing-attribute]
            )
        )
    ).scalars().all()
    if not perm_ids:
        return set()
    perms = (
        await session.execute(
            select(Permission.name).where(Permission.id.in_(perm_ids))  # ty: ignore[missing-attribute]
        )
    ).scalars().all()
    return set(perms)


class JWTAuthenticationBackend(AuthenticationBackend):
    def __init__(self, session_factory, settings: Settings):
        self._factory = session_factory
        self._settings = settings

    async def authenticate(self, conn):
        auth = conn.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return None
        token = auth.removeprefix("Bearer ")

        async with self._factory() as s:
            try:
                payload = decode_jwt(
                    token,
                    self._settings.jwt_secret.get_secret_value(),
                    self._settings.jwt_algorithm,
                )
                user_id = payload["sub"]
                user = (await s.execute(select(User).where(User.id == user_id))).scalars().first()
                if user is None:
                    return None
                perms = await load_user_permissions(s, user_id)
                return AuthCredentials(scopes=list(perms)), CurrentUser(
                    user.id, user.username, perms
                )
            except (jwt.InvalidTokenError, KeyError):
                pass

            key_row = (
                await s.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(token)))
            ).scalars().first()
            if key_row is None:
                return None
            user = (
                await s.execute(select(User).where(User.id == key_row.user_id))
            ).scalars().first()
            if user is None:
                return None
            expires = key_row.expires_at
            if expires is not None and expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if key_row.revoked_at is not None or (
                expires is not None and expires <= datetime.now(UTC)
            ):
                return None
            scopes = await load_scopes(s, key_row.id)
            return AuthCredentials(scopes=scopes), CurrentUser(
                user.id, user.username, set(scopes)
            )

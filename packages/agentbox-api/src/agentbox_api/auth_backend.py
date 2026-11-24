"""Starlette authentication backend supporting JWTs and API keys.

The backend resolves a ``Bearer`` credential to a user and attaches scopes.
JWTs are tried first; on any JWT failure the token is treated as a raw API key
and looked up by SHA-256 hash. A JWT grants the user's role-derived permissions
(``load_user_permissions``), whereas an API key grants only that key's own
scopes (``load_scopes``). Invalid, unknown, revoked, or expired credentials
yield ``None`` so the request continues as an anonymous user rather than
erroring during authentication.
"""

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
    """Authenticated user attached to a request.

    Created only after a JWT or API key resolves to a real user row, so it is
    always authenticated. ``permissions`` holds the user's role-derived
    permissions for JWT authentication, or the API key's own scopes when the
    credential is an API key.
    """

    def __init__(self, id: str, username: str, permissions: set[str]):
        self.id = id
        self.username = username
        self.permissions = permissions

    @property
    def is_authenticated(self) -> bool:
        """Always true; anonymous requests never produce a ``CurrentUser``."""
        return True

    @property
    def display_name(self) -> str:
        """Return the username shown in UIs."""
        return self.username

    @property
    def identity(self) -> str:
        """Return the user id used as the authentication identity."""
        return self.id


async def load_user_permissions(session, user_id: str) -> set[str]:
    """Return the union of permission names granted to a user's roles.

    Args:
        session: Open ``AsyncSession`` used for the role and permission queries.
        user_id: Id of the user whose permissions should be collected.

    Returns:
        The set of permission names; empty when the user has no roles or the
        roles grant no permissions.
    """
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
    """Authenticate ``Bearer`` credentials as JWTs or API keys.

    Args:
        session_factory: Factory used to open short-lived sessions for user and
            API-key lookups during authentication.
        settings: Settings supplying the JWT secret and algorithm.
    """

    def __init__(self, session_factory, settings: Settings):
        self._factory = session_factory
        self._settings = settings

    async def authenticate(self, conn):
        """Resolve the request credential to credentials and a user.

        Tries JWT verification first, then falls back to API-key lookup by the
        hash of the presented token.

        Args:
            conn: Starlette connection providing request headers.

        Returns:
            An ``(AuthCredentials, CurrentUser)`` pair, or ``None`` when the
            header is absent, malformed, or the credential is invalid, unknown,
            revoked, or expired. Returning ``None`` leaves the request anonymous.
        """
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
                # Any JWT failure falls through to API-key lookup: the token may
                # simply be an opaque key rather than a signed JWT.
                pass

            # API keys are stored only as SHA-256 hashes, so compare the hash of
            # the presented token and never the raw secret.
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
            # SQLite returns naive datetimes; treat stored expiries as UTC so the
            # comparison with ``datetime.now(UTC)`` stays timezone-consistent.
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

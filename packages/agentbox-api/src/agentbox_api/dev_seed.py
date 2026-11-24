"""Seed the local development database with an ``admin`` user.

Creates the user, an ``admin`` role, all permissions, and their links. Writes to
the configured database through the supplied session factory.
"""

import uuid

from loguru import logger
from sqlmodel import select

from agentbox_api.security import hash_password
from agentbox_models.tables.auth import (
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)

ALL_PERMISSIONS = [
    "agents:create",
    "agents:read",
    "agents:delete",
    "providers:create",
    "providers:read",
    "providers:delete",
    "providers:list-models",
    "projects:create",
    "projects:read",
    "projects:delete",
    "sessions:create",
    "sessions:read",
    "users:manage",
    "roles:manage",
    "api_keys:manage",
    "plugins:read",
    "plugins:write",
]


async def seed_admin(factory) -> None:
    """Create the development ``admin`` user and its role when absent.

    Idempotent: returns immediately when an ``admin`` user already exists, so
    repeated dev-server starts do not duplicate users, roles, or permissions.

    Args:
        factory: Async session factory bound to the target database.
    """
    async with factory() as s:
        existing = (
            await s.execute(select(User).where(User.username == "admin"))
        ).scalars().first()
        if existing is not None:
            return
        uid = uuid.uuid4().hex
        rid = uuid.uuid4().hex
        s.add(
            User(
                id=uid,
                username="admin",
                email="admin@example.com",
                password_hash=hash_password("admin"),
            )
        )
        s.add(Role(id=rid, name="admin"))
        for name in ALL_PERMISSIONS:
            pid = uuid.uuid4().hex
            s.add(Permission(id=pid, name=name))
            s.add(RolePermissionLink(role_id=rid, permission_id=pid))
        s.add(UserRoleLink(user_id=uid, role_id=rid))
        await s.commit()
        logger.info("seeded admin user")

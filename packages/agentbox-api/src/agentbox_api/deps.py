"""FastAPI dependencies for database sessions and permission checks.

Sessions come from the factory stored on ``app.state`` by
:func:`agentbox_api.app.create_app`. Permission checks read the scopes attached
by the JWT authentication middleware, so they require that middleware to be
installed for ``request.auth`` to be populated.
"""

from collections.abc import AsyncGenerator

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session bound to the current request.

    The session is opened from the app-wide session factory and closed when the
    request finishes; callers own commits and rollbacks.

    Args:
        request: Current request, used to read ``app.state.session_factory``.

    Yields:
        An ``AsyncSession`` for the duration of the request.
    """
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def require_permission(name: str):
    """Build a dependency that requires an authenticated user with a scope.

    Authentication is decided by the JWT middleware; this check only reads the
    authenticated user and its scopes. Unauthenticated requests fail with 401,
    and authenticated requests missing ``name`` fail with 403.

    Args:
        name: Permission scope required by the guarded route.

    Returns:
        An async dependency returning the authenticated user.
    """

    async def checker(request: Request):
        # ``request.user`` is AnonymousUser when the middleware rejected or did
        # not see credentials, so an authenticated check precedes scope checks.
        if not request.user.is_authenticated:
            raise HTTPException(status_code=401, detail="Unauthorized")
        scopes = request.auth.scopes if request.auth is not None else []
        if name not in scopes:
            raise HTTPException(status_code=403, detail="Forbidden")
        return request.user

    return checker

from collections.abc import AsyncGenerator

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def require_permission(name: str):
    async def checker(request: Request):
        if not request.user.is_authenticated:
            raise HTTPException(status_code=401, detail="Unauthorized")
        scopes = request.auth.scopes if request.auth is not None else []
        if name not in scopes:
            raise HTTPException(status_code=403, detail="Forbidden")
        return request.user

    return checker

from sqlalchemy import delete
from sqlmodel import select

from agentbox_models.tables.auth import ApiKeyScope


async def load_scopes(session, api_key_id: str) -> list[str]:
    rows = (
        await session.execute(
            select(ApiKeyScope.scope)
            .where(ApiKeyScope.api_key_id == api_key_id)
            .order_by(ApiKeyScope.scope)
        )
    ).scalars().all()
    return list(rows)


async def replace_scopes(session, api_key_id: str, scopes: list[str]) -> None:
    await session.execute(
        delete(ApiKeyScope).where(ApiKeyScope.api_key_id == api_key_id)
    )
    for scope in dict.fromkeys(scopes):
        session.add(ApiKeyScope(api_key_id=api_key_id, scope=scope))

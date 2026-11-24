"""Read and replace the scoped permissions attached to API keys.

Both helpers run on a caller-owned session and never commit, so the caller owns
the transaction boundary.
"""

from sqlalchemy import delete
from sqlmodel import select

from agentbox_models.tables.auth import ApiKeyScope


async def load_scopes(session, api_key_id: str) -> list[str]:
    """Return an API key's scopes in alphabetical order.

    Args:
        session: Caller-owned session; the caller controls the transaction.
        api_key_id: API key whose scopes should be listed.

    Returns:
        Scope names sorted by name, or an empty list when the key has none.
    """
    rows = (
        await session.execute(
            select(ApiKeyScope.scope)
            .where(ApiKeyScope.api_key_id == api_key_id)
            .order_by(ApiKeyScope.scope)
        )
    ).scalars().all()
    return list(rows)


async def replace_scopes(session, api_key_id: str, scopes: list[str]) -> None:
    """Replace all scopes for an API key.

    Existing rows are deleted before the new set is added, so the stored scopes
    match ``scopes`` exactly. Duplicates are collapsed while preserving the
    caller's order.

    Args:
        session: Caller-owned session; the caller must commit.
        api_key_id: API key whose scopes should be rewritten.
        scopes: Scope names to store. Duplicate entries are dropped.
    """
    await session.execute(
        delete(ApiKeyScope).where(ApiKeyScope.api_key_id == api_key_id)  # ty: ignore[invalid-argument-type]
    )
    # ``dict.fromkeys`` deduplicates while keeping the first occurrence's order.
    for scope in dict.fromkeys(scopes):
        session.add(ApiKeyScope(api_key_id=api_key_id, scope=scope))

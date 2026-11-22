import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.security import hash_api_key
from agentbox_models.repos.api_key_scopes import load_scopes, replace_scopes
from agentbox_models.tables.auth import ApiKey

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    scopes: list[str] = []
    expires_at: datetime | None = None


class ApiKeyRead(BaseModel):
    id: str
    scopes: list[str]
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class ApiKeyCreated(ApiKeyRead):
    key: str


def _read(row: ApiKey, scopes: list[str]) -> ApiKeyRead:
    return ApiKeyRead(
        id=row.id,
        scopes=scopes,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


def _normalize_expiry(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    if value <= datetime.now(UTC):
        raise HTTPException(status_code=400, detail="expires_at must be in the future")
    return value


@router.post("", response_model=ApiKeyCreated)
async def create_api_key(
    body: ApiKeyCreate,
    request: Request,
    _=Depends(require_permission("api_keys:manage")),
):
    scopes = list(dict.fromkeys(body.scopes))
    caller = set(request.auth.scopes) if request.auth is not None else set()
    disallowed = [s for s in scopes if s not in caller]
    if disallowed:
        raise HTTPException(
            status_code=400, detail=f"Unauthorized scopes: {', '.join(disallowed)}"
        )
    expires_at = _normalize_expiry(body.expires_at)
    raw = secrets.token_urlsafe(32)
    key = ApiKey(
        id=uuid.uuid4().hex,
        user_id=request.user.identity,
        key_hash=hash_api_key(raw),
        expires_at=expires_at,
    )
    async with request.app.state.session_factory() as s:
        s.add(key)
        await s.flush()
        await replace_scopes(s, key.id, scopes)
        await s.commit()
        await s.refresh(key)
    logger.info("api key created key={}", key.id)
    return ApiKeyCreated(key=raw, **_read(key, scopes).model_dump())


@router.get("", response_model=list[ApiKeyRead])
async def list_api_keys(
    request: Request, _=Depends(require_permission("api_keys:manage"))
):
    async with request.app.state.session_factory() as s:
        rows = (
            await s.execute(
                select(ApiKey).where(ApiKey.user_id == request.user.identity)
            )
        ).scalars().all()
        return [_read(row, await load_scopes(s, row.id)) for row in rows]


@router.delete("/{kid}")
async def revoke_api_key(
    kid: str, request: Request, _=Depends(require_permission("api_keys:manage"))
):
    async with request.app.state.session_factory() as s:
        row = (
            await s.execute(select(ApiKey).where(ApiKey.id == kid))
        ).scalars().first()
        if row is None or row.user_id != request.user.identity:
            raise HTTPException(status_code=404, detail="Not found")
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            s.add(row)
            await s.commit()
            logger.info("api key revoked key={}", kid)
    return {"ok": True}

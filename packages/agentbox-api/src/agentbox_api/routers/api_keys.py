import json
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.security import hash_api_key
from agentbox_models.repos.crud import ApiKeyRepository
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


def _read(row: ApiKey) -> ApiKeyRead:
    return ApiKeyRead(
        id=row.id,
        scopes=json.loads(row.scopes or "[]"),
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
    repo = ApiKeyRepository(request.app.state.session_factory)
    key = ApiKey(
        id=uuid.uuid4().hex,
        user_id=request.user.identity,
        key_hash=hash_api_key(raw),
        scopes=json.dumps(scopes),
        expires_at=expires_at,
    )
    await repo.create(key)
    return ApiKeyCreated(key=raw, **_read(key).model_dump())


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
    return [_read(r) for r in rows]


@router.delete("/{kid}")
async def delete_api_key(
    kid: str, request: Request, _=Depends(require_permission("api_keys:manage"))
):
    await ApiKeyRepository(request.app.state.session_factory).delete(kid)
    return {"ok": True}

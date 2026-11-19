import json
import secrets
import uuid

from fastapi import APIRouter, Depends, Request
from loguru import logger
from pydantic import BaseModel

from agentbox_api.deps import require_permission
from agentbox_api.security import hash_api_key
from agentbox_models.repos.crud import ApiKeyRepository
from agentbox_models.tables.auth import ApiKey

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    scopes: list[str] = []


@router.post("")
async def create_api_key(
    body: ApiKeyCreate, request: Request, _=Depends(require_permission("api_keys:manage"))
):
    raw = secrets.token_urlsafe(32)
    repo = ApiKeyRepository(request.app.state.session_factory)
    key = ApiKey(
        id=uuid.uuid4().hex,
        user_id=request.user.identity,
        key_hash=hash_api_key(raw),
        scopes=json.dumps(body.scopes),
    )
    await repo.create(key)
    logger.info("api key created key={}", key.id)
    return {"key": raw}


@router.get("")
async def list_api_keys(request: Request, _=Depends(require_permission("api_keys:manage"))):
    return await ApiKeyRepository(request.app.state.session_factory).list()


@router.delete("/{kid}")
async def delete_api_key(
    kid: str, request: Request, _=Depends(require_permission("api_keys:manage"))
):
    await ApiKeyRepository(request.app.state.session_factory).delete(kid)
    logger.info("api key deleted key={}", kid)
    return {"ok": True}

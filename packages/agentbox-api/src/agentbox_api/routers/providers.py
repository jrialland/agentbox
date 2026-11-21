import asyncio
import time
import uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.routers.models import ModelRead, model_read
from agentbox_models.repos.crud import ProviderRepository
from agentbox_models.tables.core import Agent, Model, ModelLabelLink, Provider
from agentbox_providers.models import list_models

router = APIRouter(prefix="/providers", tags=["providers"])


class ProviderCreate(BaseModel):
    name: str
    kind: str
    base_url: str | None = None
    api_key: str | None = None
    models_url: str | None = None


class ProviderRead(BaseModel):
    id: str
    name: str
    kind: str
    base_url: str | None = None
    models_url: str | None = None
    is_builtin: bool = False


class ProviderUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    models_url: str | None = None


class ProviderTestRequest(BaseModel):
    kind: str
    base_url: str | None = None
    models_url: str | None = None
    api_key: str | None = None
    provider_id: str | None = None


class ProviderTestError(BaseModel):
    code: str
    message: str


class ProviderTestResult(BaseModel):
    ok: bool
    latency_ms: int
    model_count: int | None = None
    sample_models: list[str] = []
    error: ProviderTestError | None = None


@router.post("", response_model=ProviderRead)
async def create_provider(
    body: ProviderCreate, request: Request, _=Depends(require_permission("providers:create"))
):
    provider = await ProviderRepository(request.app.state.session_factory).create(
        Provider(id=uuid.uuid4().hex, **body.model_dump())
    )
    logger.info("provider created provider={} kind={}", provider.id, provider.kind)
    return provider


@router.get("", response_model=list[ProviderRead])
async def list_providers(request: Request, _=Depends(require_permission("providers:read"))):
    return await ProviderRepository(request.app.state.session_factory).list()


def _checked_url(value: str | None, field: str) -> str | None:
    if value is None or value == "":
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=422, detail=f"{field} must be an http/https URL")
    return value


def _failure(code: str, message: str, latency_ms: int) -> ProviderTestResult:
    return ProviderTestResult(
        ok=False,
        latency_ms=latency_ms,
        error=ProviderTestError(code=code, message=message),
    )


@router.post("/test", response_model=ProviderTestResult)
async def test_provider(
    body: ProviderTestRequest,
    request: Request,
    _=Depends(require_permission("providers:create")),
):
    stored = None
    if body.provider_id:
        stored = await ProviderRepository(request.app.state.session_factory).get(
            body.provider_id
        )
        if stored is None:
            raise HTTPException(status_code=404, detail="Not found")
    base_url = _checked_url(body.base_url, "base_url")
    models_url = _checked_url(body.models_url, "models_url")
    provider = Provider(
        id=body.provider_id or "test",
        name=stored.name if stored else "test",
        kind=body.kind,
        base_url=base_url or (stored.base_url if stored else None),
        models_url=models_url or (stored.models_url if stored else None),
        api_key=body.api_key or (stored.api_key if stored else None),
    )
    if not provider.models_url:
        return _failure(
            "no_models_url",
            "Enter the endpoint that returns the provider model list.",
            0,
        )
    started = time.perf_counter()
    try:
        names = await asyncio.wait_for(list_models(provider), timeout=10)
    except TimeoutError:
        return _failure(
            "timeout",
            "The provider did not answer within 10 seconds. Check the URL and network.",
            int((time.perf_counter() - started) * 1000),
        )
    except ValueError:
        return _failure(
            "no_models_url",
            "Enter the endpoint that returns the provider model list.",
            int((time.perf_counter() - started) * 1000),
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            code = "unauthorized"
            message = "Authentication failed. Check the API key."
        elif status == 404:
            code = "not_found"
            message = "The models URL was not found. Check the path."
        else:
            code = "connection_failed"
            message = f"The provider returned HTTP {status}."
        return _failure(code, message, int((time.perf_counter() - started) * 1000))
    except httpx.RequestError:
        return _failure(
            "connection_failed",
            "Could not reach the provider. Check the URL and network.",
            int((time.perf_counter() - started) * 1000),
        )
    except Exception:
        return _failure(
            "unknown",
            "The connection test failed unexpectedly.",
            int((time.perf_counter() - started) * 1000),
        )
    latency = int((time.perf_counter() - started) * 1000)
    logger.info(
        "provider test ok provider={} kind={} count={}",
        body.provider_id,
        body.kind,
        len(names),
    )
    return ProviderTestResult(
        ok=True,
        latency_ms=latency,
        model_count=len(names),
        sample_models=names[:5],
    )


@router.put("/{pid}", response_model=ProviderRead)
async def update_provider(
    pid: str,
    body: ProviderUpdate,
    request: Request,
    _=Depends(require_permission("providers:create")),
):
    async with request.app.state.session_factory() as s:
        provider = (
            await s.execute(select(Provider).where(Provider.id == pid))
        ).scalars().first()
        if provider is None:
            raise HTTPException(status_code=404, detail="Not found")
        for field in ("name", "kind", "base_url", "api_key", "models_url"):
            value = getattr(body, field)
            if value is not None:
                setattr(provider, field, value)
        s.add(provider)
        await s.commit()
        await s.refresh(provider)
    return provider


@router.post("/{pid}/models/refresh", response_model=list[ModelRead])
async def refresh_models(
    pid: str, request: Request, _=Depends(require_permission("providers:list-models"))
):
    factory = request.app.state.session_factory
    provider = await ProviderRepository(factory).get(pid)
    if provider is None:
        raise HTTPException(status_code=404, detail="Not found")
    names = await list_models(provider)
    logger.info("models refreshed provider={} count={}", pid, len(names))
    async with factory() as s:
        existing = (
            await s.execute(select(Model).where(Model.provider_id == pid))
        ).scalars().all()
        have = {m.name for m in existing}
        for name in names:
            if name not in have:
                s.add(Model(id=uuid.uuid4().hex, provider_id=pid, name=name))
        await s.commit()
        rows = (
            await s.execute(select(Model).where(Model.provider_id == pid))
        ).scalars().all()
        result = [await model_read(s, row) for row in rows]
    return result


@router.delete("/{pid}")
async def delete_provider(
    pid: str, request: Request, _=Depends(require_permission("providers:delete"))
):
    async with request.app.state.session_factory() as s:
        provider = (
            await s.execute(select(Provider).where(Provider.id == pid))
        ).scalars().first()
        if provider is None:
            raise HTTPException(status_code=404, detail="Not found")
        models = (
            await s.execute(select(Model).where(Model.provider_id == pid))
        ).scalars().all()
        model_ids = [m.id for m in models]
        if model_ids:
            in_use = (
                await s.execute(
                    select(Agent).where(
                        Agent.model_id.in_(model_ids)  # ty: ignore[missing-attribute]
                    )
                )
            ).scalars().first()
            if in_use is not None:
                raise HTTPException(status_code=409, detail="Model in use")
            links = (
                await s.execute(
                    select(ModelLabelLink).where(
                        ModelLabelLink.model_id.in_(model_ids)  # ty: ignore[missing-attribute]
                    )
                )
            ).scalars().all()
            for link in links:
                await s.delete(link)
        for model in models:
            await s.delete(model)
        await s.delete(provider)
        await s.commit()
    return {"ok": True}



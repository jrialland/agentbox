import httpx
from loguru import logger

from agentbox_models.tables.core import Provider
from agentbox_providers.api_keys import resolve_api_key


async def _get_json(url: str, headers: dict | None = None) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return r.json()


async def list_models(provider: Provider) -> list[str]:
    if provider.models_url is None:
        raise ValueError(f"Provider {provider.name} has no models_url")
    headers = {}
    key = resolve_api_key(provider)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = await _get_json(provider.models_url, headers=headers)
    models = [item["id"] for item in data.get("data", [])]
    logger.debug("listed {} models provider={}", len(models), provider.name)
    return models

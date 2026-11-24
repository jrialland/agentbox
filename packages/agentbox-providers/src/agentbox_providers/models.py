"""List the models exposed by a provider's ``models_url`` endpoint."""

import httpx
from loguru import logger

from agentbox_models.tables.core import Provider
from agentbox_providers.api_keys import resolve_api_key


async def _get_json(url: str, headers: dict | None = None) -> dict:
    """Fetch and decode a JSON object from ``url``.

    Args:
        url: Absolute URL to request.
        headers: Optional HTTP headers to send with the request.

    Returns:
        The decoded JSON object.

    Raises:
        httpx.HTTPStatusError: If the response status is an error.
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return r.json()


async def list_models(provider: Provider) -> list[str]:
    """Return the model identifiers advertised by a provider.

    The request is sent to ``provider.models_url`` with a bearer token when an
    API key is configured.

    Args:
        provider: Provider row whose models should be listed.

    Returns:
        The model identifiers from the response ``data`` entries.

    Raises:
        ValueError: If the provider has no ``models_url``.
        httpx.HTTPStatusError: If the models request returns an error status.
    """
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

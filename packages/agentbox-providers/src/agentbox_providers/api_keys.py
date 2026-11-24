"""Resolve provider API keys from stored credentials or the environment."""

import os

from agentbox_models.tables.core import Provider


def resolve_api_key(provider: Provider) -> str | None:
    """Return the configured API key for a provider.

    The provider row takes precedence; otherwise the key is read from the
    ``{PROVIDER_NAME}_API_KEY`` environment variable.

    Args:
        provider: Provider row whose credentials should be resolved.

    Returns:
        The API key, or ``None`` when neither source is configured.
    """
    if provider.api_key:
        return provider.api_key
    env_name = f"{provider.name.upper()}_API_KEY"
    return os.environ.get(env_name)

import os

from agentbox_models.tables.core import Provider


def resolve_api_key(provider: Provider) -> str | None:
    if provider.api_key:
        return provider.api_key
    env_name = f"{provider.name.upper()}_API_KEY"
    return os.environ.get(env_name)

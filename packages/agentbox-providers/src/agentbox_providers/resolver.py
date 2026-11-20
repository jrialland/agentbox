from loguru import logger
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from agentbox_models.tables.core import Provider
from agentbox_providers.api_keys import resolve_api_key


def resolve_model(
    provider: Provider, model_name: str, context_window: int | None = None
) -> Model:
    kind = provider.kind
    profile: ModelProfile | None = (
        {"context_window": context_window} if context_window else None
    )
    logger.debug("resolving model provider={} kind={} model={}", provider.name, kind, model_name)
    if kind == "openai_legacy":
        return OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(api_key=resolve_api_key(provider)),
            profile=profile,
        )
    if kind == "openai_responses":
        return OpenAIResponsesModel(
            model_name,
            provider=OpenAIProvider(api_key=resolve_api_key(provider)),
            profile=profile,
        )
    if kind == "anthropic":
        return AnthropicModel(
            model_name,
            provider=AnthropicProvider(api_key=resolve_api_key(provider)),
            profile=profile,
        )
    if kind in ("generic", "moonshot", "deepseek"):
        return OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(
                base_url=provider.base_url, api_key=resolve_api_key(provider)
            ),
            profile=profile,
        )
    if kind == "ollama":
        return OllamaModel(
            model_name,
            provider=OllamaProvider(base_url=provider.base_url),
            profile=profile,
        )
    if kind == "test":
        from pydantic_ai.models.test import TestModel

        return TestModel(
            call_tools=[],
            custom_output_text="Hello from the test provider",
            profile=profile,
        )
    if kind == "test_tool":
        from pydantic_ai.models.test import TestModel

        return TestModel(
            call_tools=["show_app"],
            custom_output_text="Hello from the test provider",
            profile=profile,
        )
    raise ValueError(f"Unknown provider kind: {kind}")

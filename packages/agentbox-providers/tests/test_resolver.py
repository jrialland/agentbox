import pytest
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.models.test import TestModel

from agentbox_models.tables.core import Provider
from agentbox_providers.resolver import resolve_model


def test_resolve_ollama():
    m = resolve_model(
        Provider(id="p", name="ollama", kind="ollama", base_url="http://localhost:11434"),
        "gemma4:e2b",
    )
    assert isinstance(m, OllamaModel)


def test_resolve_openai_legacy():
    m = resolve_model(
        Provider(id="p", name="openai", kind="openai_legacy", api_key="sk-test"), "gpt-4o"
    )
    assert isinstance(m, OpenAIChatModel)


def test_resolve_openai_responses():
    m = resolve_model(
        Provider(id="p", name="openai", kind="openai_responses", api_key="sk-test"), "gpt-4o"
    )
    assert isinstance(m, OpenAIResponsesModel)


def test_resolve_anthropic():
    m = resolve_model(
        Provider(id="p", name="anthropic", kind="anthropic", api_key="sk-test"), "claude-x"
    )
    assert isinstance(m, AnthropicModel)


def test_resolve_generic():
    m = resolve_model(
        Provider(id="p", name="gen", kind="generic", base_url="https://x/v1"), "m"
    )
    assert isinstance(m, OpenAIChatModel)


def test_resolve_moonshot():
    m = resolve_model(
        Provider(id="p", name="moonshot", kind="moonshot", base_url="https://api.moonshot.cn/v1"),
        "moonshot-v1-8k",
    )
    assert isinstance(m, OpenAIChatModel)


def test_resolve_test_provider_does_not_call_tools():
    m = resolve_model(Provider(id="p", name="test", kind="test"), "test-model")
    assert isinstance(m, TestModel)
    assert m.call_tools == []


def test_resolve_context_window_override():
    m = resolve_model(
        Provider(id="p", name="openai", kind="openai_legacy", api_key="sk-test"),
        "custom-model",
        context_window=123_456,
    )
    assert m.profile["context_window"] == 123_456


def test_resolve_known_model_profile_is_used_without_override():
    m = resolve_model(
        Provider(id="p", name="openai", kind="openai_legacy", api_key="sk-test"),
        "gpt-4o",
    )
    assert m.profile["context_window"] == 128_000


def test_resolve_unknown_kind_raises():
    with pytest.raises(ValueError):
        resolve_model(Provider(id="p", name="x", kind="bogus"), "m")

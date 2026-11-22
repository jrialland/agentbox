import asyncio

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

_flaky_attempts: dict[str, int] = {}

_LONG_FIXTURE_TEXT = (
    "# Long fixture\n\n"
    + (
        "Agentbox streams a message through the harness, the model, and the tool layer, "
        "then renders the answer as Markdown with headings, lists, tables, and diagrams. "
    )
    * 30
    + "\n\n## Wide diagram\n\n"
    "```mermaid\nflowchart LR\n  Composer --> Agent\n  Agent --> Model\n"
    "  Model --> Tools\n  Tools --> Reply\n```\n\n"
    "## Table\n\n| Step | Owner |\n| --- | --- |\n| Compose | User |\n"
    "| Stream | Harness |\n| Answer | Model |\n"
)


def resolve_model(
    provider: Provider, model_name: str, context_window: int | None = None
) -> Model:
    kind = provider.kind
    profile: ModelProfile | None = (
        {"context_window": context_window} if context_window else None
    )
    logger.debug(
        "resolving model provider={} kind={} model={}",
        provider.name,
        kind,
        model_name,
    )
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
    if kind == "test_acp_fs":
        from pydantic_ai.models.function import DeltaToolCall, FunctionModel

        async def fs_stream(messages, info):
            has_tool_result = any(
                getattr(part, "part_kind", "") == "tool-return"
                for message in messages
                for part in message.parts
            )
            if not has_tool_result:
                yield {
                    0: DeltaToolCall(
                        name="read_text_file",
                        json_args='{"path": "hello.txt"}',
                        tool_call_id="fs-call",
                    )
                }
                return
            yield "FS done"

        return FunctionModel(
            stream_function=fs_stream, model_name=model_name, profile=profile
        )
    if kind == "test_acp_terminal":
        from pydantic_ai.models.function import DeltaToolCall, FunctionModel

        async def terminal_stream(messages, info):
            has_tool_result = any(
                getattr(part, "part_kind", "") == "tool-return"
                for message in messages
                for part in message.parts
            )
            if not has_tool_result:
                yield {
                    0: DeltaToolCall(
                        name="run_command",
                        json_args='{"command": "echo hi"}',
                        tool_call_id="terminal-call",
                    )
                }
                return
            yield "Terminal done"

        return FunctionModel(
            stream_function=terminal_stream, model_name=model_name, profile=profile
        )
    if kind == "test_markdown":
        from pydantic_ai.models.test import TestModel

        return TestModel(
            call_tools=[],
            custom_output_text=(
                "# Chat UX\n\n"
                "| Feature | State |\n| --- | --- |\n| Markdown | ok |\n\n"
                '```python\nprint("hi")\n```\n\n'
                "```mermaid\ngraph TD; A-->B\n```\n\n"
                "```mermaid\nthis is not a diagram\n```"
            ),
            profile=profile,
        )
    if kind == "test_tool_slow":
        from pydantic_ai.models.function import DeltaToolCall, FunctionModel

        async def tool_slow(messages, info):
            has_tool_result = any(
                getattr(part, "part_kind", "") == "tool-return"
                for message in messages
                for part in message.parts
            )
            if not has_tool_result:
                yield {
                    0: DeltaToolCall(
                        name="show_app", json_args="{}", tool_call_id="app-call"
                    )
                }
                return
            for chunk in ("Tool ", "ran. ", "Final ", "answer"):
                await asyncio.sleep(0.8)
                yield chunk

        return FunctionModel(
            stream_function=tool_slow, model_name=model_name, profile=profile
        )
    if kind == "test_slow":
        from pydantic_ai.models.function import FunctionModel

        async def slow_stream(messages, info):
            for chunk in ("Partial ", "answer ", "still ", "running"):
                await asyncio.sleep(0.8)
                yield chunk

        return FunctionModel(
            stream_function=slow_stream, model_name=model_name, profile=profile
        )
    if kind == "test_error":
        from pydantic_ai.models.function import FunctionModel

        async def error_stream(messages, info):
            yield "Partial "
            await asyncio.sleep(0.1)
            raise RuntimeError("provider exploded")

        return FunctionModel(
            stream_function=error_stream, model_name=model_name, profile=profile
        )
    if kind == "test_flaky":
        from pydantic_ai.models.function import FunctionModel

        async def flaky_stream(messages, info):
            attempts = _flaky_attempts.get(model_name, 0) + 1
            _flaky_attempts[model_name] = attempts
            if attempts == 1:
                raise RuntimeError("provider exploded once")
            yield "Recovered answer"

        return FunctionModel(
            stream_function=flaky_stream, model_name=model_name, profile=profile
        )
    if kind == "test_long":
        from pydantic_ai.models.test import TestModel

        return TestModel(
            call_tools=[],
            custom_output_text=_LONG_FIXTURE_TEXT,
            profile=profile,
        )
    raise ValueError(f"Unknown provider kind: {kind}")



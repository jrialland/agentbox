from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.session import InMemoryMessageLogStore
from agentbox_harness.spec import (
    DEFAULT_MODES,
    AgentSpec,
    ModelBinding,
    NativeToolBinding,
)
from agentbox_harness.tools.filesystem import FilesystemToolbox
from agentbox_harness.tools.registry import ToolRegistry


def _has_tool_return(messages) -> bool:
    return any(
        getattr(part, "part_kind", "") == "tool-return"
        for message in messages
        for part in message.parts
    )


async def test_tool_error_is_returned_to_model(tmp_path):
    (tmp_path / "file.txt").write_text("a\nb\n", encoding="utf-8")
    box = FilesystemToolbox(tmp_path)
    registry = ToolRegistry()
    registry.register_native("read_text_file", box.read_text_file)

    spec = AgentSpec(
        name="coder",
        description="d",
        instructions="i",
        tool_bindings=[NativeToolBinding(name="read_text_file")],
        mode_definitions=list(DEFAULT_MODES),
        model_binding=ModelBinding(model="test", provider="test"),
    )
    harness = Harness(
        registry=registry,
        model=TestModel(),
        store_factory=InMemoryMessageLogStore,
    )
    session = harness.start_session(spec, project_root=str(tmp_path), mode_name="agent")
    captured = []

    async def stream_fn(messages, info):
        captured.append(messages)
        if not _has_tool_return(messages):
            yield {
                0: DeltaToolCall(
                    name="read_text_file",
                    json_args='{"path": "file.txt", "head": 1, "tail": 1}',
                    tool_call_id="call-1",
                )
            }
            return
        yield "Recovered"

    outcome = await harness.run_turn(
        session,
        "read the file",
        bus=EventBus(),
        model_override=FunctionModel(stream_function=stream_fn),
    )

    assert outcome.status == "success", outcome
    history = await session.history()
    assert history[-1].role == "assistant"
    assert history[-1].content == "Recovered"
    tool_returns = [
        getattr(part, "content", "")
        for message in captured[-1]
        for part in message.parts
        if getattr(part, "part_kind", "") == "tool-return"
    ]
    assert any("mutually exclusive" in str(content) for content in tool_returns)

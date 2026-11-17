from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.session import InMemoryMessageLogStore, Turn
from agentbox_harness.spec import (
    DEFAULT_MODES,
    AgentSpec,
    ModelBinding,
    NativeToolBinding,
)
from agentbox_harness.tools.registry import ToolRegistry


async def write_file(path: str, content: str) -> str:
    return "ok"


def _spec() -> AgentSpec:
    return AgentSpec(
        name="coder",
        description="d",
        instructions="i",
        tool_bindings=[NativeToolBinding(name="write_file")],
        mode_definitions=list(DEFAULT_MODES),
        model_binding=ModelBinding(model="test", provider="test"),
    )


async def test_harness_passes_prior_history():
    captured = []

    async def stream_fn(messages, info):
        captured.extend(messages)
        yield "done"

    reg = ToolRegistry()
    reg.register_native("write_file", write_file, required_flags=("write",))

    harness = Harness(registry=reg, model=TestModel(), store_factory=InMemoryMessageLogStore)
    session = harness.start_session(_spec(), project_root=".", mode_name="agent")

    await session.store.append(
        Turn(id="u1", role="user", content="first question", parent_id=None)
    )
    await session.store.append(
        Turn(id="a1", role="assistant", content="first answer", parent_id="u1")
    )
    session.head_id = "a1"

    bus = EventBus()
    run = await harness.run(
        session,
        "second question",
        bus=bus,
        model_override=FunctionModel(stream_function=stream_fn),
    )
    await run.await_outcome()

    contents = []
    for msg in captured:
        for part in msg.parts:
            content = getattr(part, "content", None)
            if isinstance(content, str):
                contents.append(content)

    assert "first question" in contents
    assert "first answer" in contents

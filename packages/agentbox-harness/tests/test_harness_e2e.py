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
from agentbox_harness.tools.registry import ToolRegistry


async def write_file(path: str, content: str) -> str:
    return "ok"


def _spec() -> AgentSpec:
    return AgentSpec(
        name="coder",
        description="writes code",
        instructions="Be helpful.",
        tool_bindings=[NativeToolBinding(name="write_file")],
        mode_definitions=list(DEFAULT_MODES),
        model_binding=ModelBinding(model="test", provider="test"),
    )


async def test_harness_runs_a_session():
    reg = ToolRegistry()
    reg.register_native("write_file", write_file, required_flags=("write",))

    harness = Harness(registry=reg, model="test", store_factory=InMemoryMessageLogStore)
    session = harness.start_session(_spec(), project_root=".", mode_name="agent")

    bus = EventBus()
    run = await harness.run(session, "write a file", bus=bus, model_override=TestModel())
    result = await run.await_result()

    assert result.output is not None
    assert (await session.history())[-1].role == "user"

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
        description="d",
        instructions="i",
        tool_bindings=[NativeToolBinding(name="write_file")],
        mode_definitions=list(DEFAULT_MODES),
        model_binding=ModelBinding(model="test", provider="test"),
    )


async def test_run_turn_records_assistant_turn():
    reg = ToolRegistry()
    reg.register_native("write_file", write_file, required_flags=("write",))

    harness = Harness(registry=reg, model=TestModel(), store_factory=InMemoryMessageLogStore)
    session = harness.start_session(_spec(), project_root=".", mode_name="agent")

    bus = EventBus()
    outcome = await harness.run_turn(
        session, "hello", bus=bus, model_override=TestModel()
    )

    assert outcome.status == "success"
    assert [t.role for t in await session.history()] == ["user", "assistant"]

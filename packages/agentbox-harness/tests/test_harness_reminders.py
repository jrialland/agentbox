from types import SimpleNamespace

from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.harness import Harness
from agentbox_harness.session import InMemoryMessageLogStore
from agentbox_harness.spec import (
    DEFAULT_MODES,
    AgentSpec,
    ModelBinding,
)
from agentbox_harness.tools.registry import ToolRegistry


class FakeReminder:
    def __init__(self, text):
        self.text = text

    async def reminder(self, session):
        return self.text


class CapturingRunManager:
    def __init__(self):
        self.prompt: str = ""
        self.kwargs: dict = {}

    def start(self, agent, prompt, **kwargs):
        self.prompt = prompt
        self.kwargs = kwargs
        return SimpleNamespace()


def _spec() -> AgentSpec:
    return AgentSpec(
        name="coder",
        description="d",
        instructions="i",
        tool_bindings=[],
        mode_definitions=list(DEFAULT_MODES),
        model_binding=ModelBinding(model="test", provider="test"),
    )


def _harness(reminders):
    return Harness(
        registry=ToolRegistry(),
        model=TestModel(),
        store_factory=InMemoryMessageLogStore,
        reminders=reminders,
    )


async def test_reminder_is_appended_to_prompt(tmp_path):
    harness = _harness([FakeReminder("<lsp_diagnostics>boom</lsp_diagnostics>")])
    run_manager = CapturingRunManager()
    harness.run_manager = run_manager
    session = harness.start_session(_spec(), project_root=str(tmp_path), mode_name="agent")

    await harness.run(session, "hello", EventBus())

    assert run_manager.prompt.endswith("boom</lsp_diagnostics>")
    history = await session.history()
    assert history[-1].content == "hello"


async def test_reminder_is_appended_to_prompt_override(tmp_path):
    harness = _harness([FakeReminder("<lsp_diagnostics>boom</lsp_diagnostics>")])
    run_manager = CapturingRunManager()
    harness.run_manager = run_manager
    session = harness.start_session(_spec(), project_root=str(tmp_path), mode_name="agent")

    await harness.run(session, "hello", EventBus(), prompt_override=["part"])

    assert run_manager.prompt.startswith("hello")
    assert run_manager.kwargs["prompt_override"][0] == "part"
    assert "boom" in run_manager.kwargs["prompt_override"][-1]


async def test_multiple_reminders_join_with_blank_line(tmp_path):
    harness = _harness([FakeReminder("one"), FakeReminder("two")])
    run_manager = CapturingRunManager()
    harness.run_manager = run_manager
    session = harness.start_session(_spec(), project_root=str(tmp_path), mode_name="agent")

    await harness.run(session, "hello", EventBus())

    assert run_manager.prompt.endswith("one\n\ntwo")


async def test_failing_reminder_is_ignored(tmp_path):
    class Broken:
        async def reminder(self, session):
            raise RuntimeError("boom")

    harness = _harness([Broken(), FakeReminder("ok")])
    run_manager = CapturingRunManager()
    harness.run_manager = run_manager
    session = harness.start_session(_spec(), project_root=str(tmp_path), mode_name="agent")

    await harness.run(session, "hello", EventBus())

    assert run_manager.prompt.endswith("ok")

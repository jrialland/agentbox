from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.test import TestModel

from agentbox_harness.events import EventBus
from agentbox_harness.middleware import MiddlewarePipeline, RunContext
from agentbox_harness.session import InMemoryMessageLogStore, Session


def _ctx() -> RunContext:
    session = Session(
        session_id="s1",
        project_root=".",
        agent_spec=None,
        store=InMemoryMessageLogStore(),
        head_id=None,
    )
    return RunContext(
        session=session, model=TestModel(), bus=EventBus(), prompt="hi"
    )


class Fake:
    def __init__(self, name, history=None):
        self.name = name
        self.calls = []
        self.history = history

    async def before_run(self, ctx):
        self.calls.append("before")

    async def on_context_overflow(self, ctx) -> list[ModelMessage] | None:
        self.calls.append("recover")
        return self.history


async def test_prepare_runs_before_run_in_order():
    first, second = Fake("first"), Fake("second")
    pipeline = MiddlewarePipeline([first, second])
    await pipeline.prepare(_ctx())
    assert first.calls == ["before"]
    assert second.calls == ["before"]


async def test_recover_returns_first_non_none():
    first = Fake("first", history=[])
    second = Fake("second", history=[])
    pipeline = MiddlewarePipeline([first, second])
    assert await pipeline.recover(_ctx()) == []
    assert first.calls == ["recover"]
    assert second.calls == []

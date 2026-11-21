from pydantic_ai.models.test import TestModel

from agentbox_harness.harness import Harness
from agentbox_harness.session import InMemoryMessageLogStore, Session
from agentbox_harness.spec import (
    AgentSpec,
    McpToolBinding,
    ModelBinding,
)
from agentbox_harness.tools.mcp_session import McpSessionManager, SessionToolsets
from agentbox_harness.tools.registry import ToolRegistry


class FakeManager(McpSessionManager):
    def __init__(self):
        self.calls = []
        self.result = SessionToolsets()

    async def toolsets_for(self, session_id, bindings, project_root, extra_roots=None):
        self.calls.append((session_id, bindings, project_root, extra_roots))
        return self.result


def _spec() -> AgentSpec:
    return AgentSpec(
        name="coder",
        description="",
        instructions="",
        tool_bindings=[McpToolBinding(id="local", command="python")],
        model_binding=ModelBinding(model="test", provider="test"),
    )


def test_session_has_extra_roots_default():
    session = Session(
        session_id="s1",
        project_root="/tmp",
        agent_spec=None,
        store=InMemoryMessageLogStore(),
        head_id=None,
    )
    assert session.extra_roots == []


async def test_harness_prepare_mcp_uses_session_roots():
    manager = FakeManager()
    harness = Harness(
        registry=ToolRegistry(),
        model=TestModel(),
        store_factory=InMemoryMessageLogStore,
        mcp_manager=manager,
    )
    session = Session(
        session_id="s1",
        project_root="/tmp/project",
        agent_spec=_spec(),
        store=InMemoryMessageLogStore(),
        head_id=None,
        extra_roots=["/tmp/extra"],
    )

    result = await harness.prepare_mcp(session)

    assert result is manager.result
    assert manager.calls == [
        ("s1", [_spec().tool_bindings[0]], "/tmp/project", ["/tmp/extra"])
    ]

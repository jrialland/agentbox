from agentbox_harness.agent_factory import build_sub_session_tools
from agentbox_harness.spec import AgentSpec, Mode, ModelBinding
from agentbox_harness.subagents import make_sub_session_tools


def _spec(name="parent", subs=None) -> AgentSpec:
    return AgentSpec(
        name=name,
        description="d",
        instructions="i",
        tool_bindings=[],
        sub_agent_ids=subs or [],
        model_binding=ModelBinding(model="test", provider="test"),
    )


class FakeRunner:
    def __init__(self):
        self.calls = []

    async def start(self, parent_session_id, parent_spec, agent_name, task, wait):
        self.calls.append(("start", parent_session_id, agent_name, task, wait))
        return f"started {agent_name}"

    async def list(self, parent_session_id):
        self.calls.append(("list", parent_session_id))
        return "no children"

    async def get(self, parent_session_id, sub_session_id, max_chars):
        self.calls.append(("get", parent_session_id, sub_session_id, max_chars))
        return "child"

    async def cancel(self, parent_session_id, sub_session_id):
        self.calls.append(("cancel", parent_session_id, sub_session_id))
        return "cancelled"


async def test_tools_validate_and_delegate():
    runner = FakeRunner()
    tools = make_sub_session_tools(runner, "parent-1", _spec(subs=["sub"]))
    assert await tools["start_sub_session"]("sub", "do it") == "started sub"
    assert runner.calls[-1] == ("start", "parent-1", "sub", "do it", False)
    assert "unknown agent" in await tools["start_sub_session"]("other", "do it")
    assert "must not be empty" in await tools["start_sub_session"]("sub", "  ")
    assert await tools["list_sub_sessions"]() == "no children"
    assert await tools["get_sub_session"]("child-1") == "child"
    assert await tools["cancel_sub_session"]("child-1") == "cancelled"


def test_tools_are_gated_by_subagents_and_write_mode():
    runner = FakeRunner()
    agent_mode = Mode(name="agent", flags={"write": True})
    ask_mode = Mode(name="ask", flags={"write": False})
    assert build_sub_session_tools(_spec(subs=["sub"]), agent_mode, runner, "s1")
    assert build_sub_session_tools(_spec(subs=["sub"]), ask_mode, runner, "s1") == []
    assert build_sub_session_tools(_spec(subs=[]), agent_mode, runner, "s1") == []
    assert build_sub_session_tools(_spec(subs=["sub"]), agent_mode, None, "s1") == []

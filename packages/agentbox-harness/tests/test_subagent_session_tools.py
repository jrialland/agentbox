from agentbox_harness.agent_factory import build_subagent_session_tools
from agentbox_harness.spec import Mode
from agentbox_harness.subagent_sessions import make_subagent_session_tools


class FakeRunner:
    def __init__(self):
        self.calls = []

    async def list_agents(self):
        self.calls.append(("list_agents",))
        return "Agents:\n- child: helper"

    async def start(self, parent_session_id, subagent, task, wait):
        self.calls.append(("start", parent_session_id, subagent, task, wait))
        return f"started {subagent}"

    async def list(self, parent_session_id):
        self.calls.append(("list", parent_session_id))
        return "children"

    async def get(self, parent_session_id, subagent_session_id, max_chars):
        self.calls.append(("get", parent_session_id, subagent_session_id, max_chars))
        return "child"

    async def cancel(self, parent_session_id, subagent_session_id):
        self.calls.append(("cancel", parent_session_id, subagent_session_id))
        return "cancelled"

    async def wait(self, parent_session_id, subagent_session_id, timeout):
        self.calls.append(("wait", parent_session_id, subagent_session_id, timeout))
        return "waited"

    async def wait_many(self, parent_session_id, subagent_session_ids, mode, timeout):
        self.calls.append(
            ("wait_many", parent_session_id, subagent_session_ids, mode, timeout)
        )
        return "waited any"


async def test_tools_use_subagent_session_names_and_validate_task():
    runner = FakeRunner()
    tools = make_subagent_session_tools(runner, "parent-1")

    assert await tools["list_agents"]() == "Agents:\n- child: helper"
    assert await tools["start_subagent_session"]("child", "do it") == "started child"
    assert runner.calls[-1] == ("start", "parent-1", "child", "do it", False)
    assert "must not be empty" in await tools["start_subagent_session"]("child", "  ")
    assert await tools["list_subagent_sessions"]() == "children"
    assert await tools["get_subagent_session"]("child-1") == "child"
    assert await tools["cancel_subagent_session"]("child-1") == "cancelled"
    assert await tools["wait_subagent_session"]("child-1", 5) == "waited"
    assert (
        await tools["wait_subagent_sessions"](["child-1"], "any", 5)
        == "waited any"
    )


def test_bundle_is_write_mode_only_and_needs_runner_and_session():
    runner = FakeRunner()
    agent_mode = Mode(name="agent", flags={"write": True})
    ask_mode = Mode(name="ask", flags={"write": False})

    assert build_subagent_session_tools(agent_mode, runner, "s1")
    assert build_subagent_session_tools(ask_mode, runner, "s1") == []
    assert build_subagent_session_tools(agent_mode, None, "s1") == []
    assert build_subagent_session_tools(agent_mode, runner, None) == []

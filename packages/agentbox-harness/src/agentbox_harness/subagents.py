from collections.abc import Callable
from typing import Protocol

from loguru import logger
from pydantic_ai import Agent, RunContext

from agentbox_harness.spec import AgentSpec, Mode


def build_subagent_tool(sub_agent: Agent) -> Callable:
    async def delegate(ctx: RunContext, task: str) -> str:
        logger.debug("subagent delegated name={}", sub_agent.name)
        result = await sub_agent.run(task, usage=ctx.usage)
        return str(result.output)

    delegate.__name__ = f"delegate_{sub_agent.name}"
    return delegate


class SubSessionRunner(Protocol):
    async def start(
        self,
        parent_session_id: str,
        parent_spec: AgentSpec,
        agent_name: str,
        task: str,
        wait: bool,
    ) -> str: ...

    async def list(self, parent_session_id: str) -> str: ...

    async def get(
        self, parent_session_id: str, sub_session_id: str, max_chars: int
    ) -> str: ...

    async def cancel(self, parent_session_id: str, sub_session_id: str) -> str: ...


def make_sub_session_tools(
    runner: SubSessionRunner,
    parent_session_id: str,
    parent_spec: AgentSpec,
) -> dict[str, Callable]:
    allowed = set(parent_spec.sub_agent_ids)

    async def start_sub_session(agent: str, task: str, wait: bool = False) -> str:
        text = (task or "").strip()
        if not text:
            return "Sub-session failed: task must not be empty."
        if agent not in allowed:
            names = ", ".join(sorted(allowed)) or "(none)"
            return f"Sub-session failed: unknown agent {agent}. Available: {names}"
        return await runner.start(parent_session_id, parent_spec, agent, text, wait)

    async def list_sub_sessions() -> str:
        return await runner.list(parent_session_id)

    async def get_sub_session(sub_session_id: str, max_chars: int = 4000) -> str:
        return await runner.get(parent_session_id, sub_session_id, max_chars)

    async def cancel_sub_session(sub_session_id: str) -> str:
        return await runner.cancel(parent_session_id, sub_session_id)

    return {
        "start_sub_session": start_sub_session,
        "list_sub_sessions": list_sub_sessions,
        "get_sub_session": get_sub_session,
        "cancel_sub_session": cancel_sub_session,
    }


def build_sub_session_tools(
    spec: AgentSpec,
    mode: Mode,
    runner: SubSessionRunner | None,
    session_id: str | None,
) -> list[Callable]:
    if runner is None or not spec.sub_agent_ids or not session_id:
        return []
    if not mode.allows("write"):
        return []
    return list(make_sub_session_tools(runner, session_id, spec).values())

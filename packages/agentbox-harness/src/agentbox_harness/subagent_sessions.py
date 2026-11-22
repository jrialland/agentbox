from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from agentbox_harness.spec import Mode


class SubagentSessionRunner(Protocol):
    async def list_agents(self) -> str: ...

    async def start(
        self, parent_session_id: str, subagent: str, task: str, wait: bool
    ) -> str: ...

    async def list(self, parent_session_id: str) -> str: ...

    async def get(
        self, parent_session_id: str, subagent_session_id: str, max_chars: int
    ) -> str: ...

    async def cancel(
        self, parent_session_id: str, subagent_session_id: str
    ) -> str: ...

    async def wait(
        self, parent_session_id: str, subagent_session_id: str, timeout: int
    ) -> str: ...

    async def wait_many(
        self,
        parent_session_id: str,
        subagent_session_ids: Sequence[str],
        mode: str,
        timeout: int,
    ) -> str: ...


def make_subagent_session_tools(
    runner: SubagentSessionRunner, parent_session_id: str
) -> dict[str, Callable]:
    async def list_agents() -> str:
        """List agent configurations available as subagents."""
        return await runner.list_agents()

    async def start_subagent_session(
        subagent: str, task: str, wait: bool = False
    ) -> str:
        """Start a subagent session using the named agent configuration.

        The agent configuration is the subagent; the child session is the
        subagent session. Returns the session id immediately unless wait=True.
        """
        text = (task or "").strip()
        if not text:
            return "Subagent session failed: task must not be empty."
        return await runner.start(parent_session_id, subagent.strip(), text, wait)

    async def list_subagent_sessions() -> str:
        """List this session's subagent sessions with status and task summary."""
        return await runner.list(parent_session_id)

    async def get_subagent_session(
        subagent_session_id: str, max_chars: int = 4000
    ) -> str:
        """Read a subagent session's status and live or final output."""
        return await runner.get(parent_session_id, subagent_session_id, max_chars)

    async def cancel_subagent_session(subagent_session_id: str) -> str:
        """Cancel a subagent session and its descendants."""
        return await runner.cancel(parent_session_id, subagent_session_id)

    async def wait_subagent_session(
        subagent_session_id: str, timeout: int = 30
    ) -> str:
        """Wait for one subagent session to finish or time out."""
        return await runner.wait(parent_session_id, subagent_session_id, timeout)

    async def wait_subagent_sessions(
        subagent_session_ids: list[str],
        mode: str = "all",
        timeout: int = 60,
    ) -> str:
        """Wait for all or any listed subagent sessions to finish or time out."""
        return await runner.wait_many(
            parent_session_id, subagent_session_ids, mode, timeout
        )

    return {
        "list_agents": list_agents,
        "start_subagent_session": start_subagent_session,
        "list_subagent_sessions": list_subagent_sessions,
        "get_subagent_session": get_subagent_session,
        "cancel_subagent_session": cancel_subagent_session,
        "wait_subagent_session": wait_subagent_session,
        "wait_subagent_sessions": wait_subagent_sessions,
    }


def build_subagent_session_tools(
    mode: Mode,
    runner: SubagentSessionRunner | None,
    session_id: str | None,
) -> list[Callable]:
    if runner is None or not session_id or not mode.allows("write"):
        return []
    return list(make_subagent_session_tools(runner, session_id).values())

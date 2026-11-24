"""Subagent-session tools exposed to an agent running in write mode.

:class:`SubagentSessionRunner` is the runtime contract and the tool factory
wraps a runner into the canonical ``*_subagent_session(s)`` tools. The parent
session owns creation, waiting, and cancellation of its child sessions; the
runner owns execution.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from agentbox_harness.spec import Mode


class SubagentSessionRunner(Protocol):
    """Runtime contract for starting, inspecting, and cancelling child sessions.

    Implementations execute subagent sessions and return string results
    suitable for direct use as tool output.
    """

    async def list_agents(self) -> str: ...  # noqa: D102

    async def start(  # noqa: D102
        self, parent_session_id: str, subagent: str, task: str, wait: bool
    ) -> str: ...

    async def list(self, parent_session_id: str) -> str: ...  # noqa: D102

    async def get(  # noqa: D102
        self, parent_session_id: str, subagent_session_id: str, max_chars: int
    ) -> str: ...

    async def cancel(  # noqa: D102
        self, parent_session_id: str, subagent_session_id: str
    ) -> str: ...

    async def wait(  # noqa: D102
        self, parent_session_id: str, subagent_session_id: str, timeout: int
    ) -> str: ...

    async def wait_many(  # noqa: D102
        self,
        parent_session_id: str,
        subagent_session_ids: Sequence[str],
        mode: str,
        timeout: int,
    ) -> str: ...


def make_subagent_session_tools(
    runner: SubagentSessionRunner, parent_session_id: str
) -> dict[str, Callable]:
    """Build the canonical subagent-session tools for a parent session.

    Every returned tool forwards to ``runner`` scoped to
    ``parent_session_id``, so the parent session owns creation and cancellation
    while the runner owns execution. Task text is validated before a session is
    started.

    Args:
        runner: Runtime that executes subagent sessions.
        parent_session_id: Parent session id the tools act on behalf of.

    Returns:
        Tool callables keyed by canonical tool name.
    """

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
        # The parent session owns creation; the runner executes the child
        # session and reports its id (or the waited result) back.
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
        # Cancellation is scoped to the child and its descendants; the runner
        # enforces ownership against the parent session id.
        return await runner.cancel(parent_session_id, subagent_session_id)

    async def wait_subagent_session(
        subagent_session_id: str, timeout: int = 30
    ) -> str:
        """Wait for one subagent session to finish or time out."""
        # Waiting is bounded by the caller's timeout; completion or timeout is
        # reported as text by the runner.
        return await runner.wait(parent_session_id, subagent_session_id, timeout)

    async def wait_subagent_sessions(
        subagent_session_ids: list[str],
        mode: str = "all",
        timeout: int = 60,
    ) -> str:
        """Wait for all or any listed subagent sessions to finish or time out."""
        # ``mode`` selects whether every session or only one must finish, still
        # bounded by the shared timeout.
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
    """Return subagent-session tools when the mode and runner allow them.

    Tools are exposed only in write modes with a runner and session id so
    read-only or unwired sessions get no subagent-session tools.

    Args:
        mode: Mode whose flags gate subagent-session tools.
        runner: Subagent-session runner, or ``None`` when unwired.
        session_id: Parent session id, or ``None`` when no session is bound.

    Returns:
        Tool callables to register, or an empty list when unavailable.
    """
    if runner is None or not session_id or not mode.allows("write"):
        return []
    return list(make_subagent_session_tools(runner, session_id).values())

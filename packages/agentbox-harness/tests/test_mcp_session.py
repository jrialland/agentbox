import pathlib
import sys

import pytest_asyncio

from agentbox_harness.spec import McpToolBinding
from agentbox_harness.tools.mcp_session import (
    McpSessionManager,
    get_mcp_session_manager,
    reset_mcp_session_manager,
)

SERVER = pathlib.Path(__file__).with_name("stdio_mcp_server.py")


def _binding(server_id: str = "echo") -> McpToolBinding:
    return McpToolBinding(
        id=server_id,
        command=sys.executable,
        args=[str(SERVER)],
    )


@pytest_asyncio.fixture(autouse=True)
async def _manager():
    reset_mcp_session_manager()
    yield
    await get_mcp_session_manager().close_all()
    reset_mcp_session_manager()


async def test_starts_once_and_reuses(tmp_path):
    manager = McpSessionManager(start_timeout=20)
    first = await manager.toolsets_for("s1", [_binding()], str(tmp_path))
    second = await manager.toolsets_for("s1", [_binding("changed")], str(tmp_path))

    assert len(first.toolsets) == 1
    assert first.warnings == []
    assert second.toolsets[0] is first.toolsets[0]
    assert manager._entries["s1"].bindings[0].id == "echo"

    await manager.close_session("s1")


async def test_pins_empty_stdio_set(tmp_path):
    manager = McpSessionManager(start_timeout=20)
    first = await manager.toolsets_for("s1", [], str(tmp_path))
    second = await manager.toolsets_for("s1", [_binding()], str(tmp_path))

    assert first.toolsets == []
    assert second.toolsets == []
    assert "s1" in manager._entries

    await manager.close_session("s1")


async def test_concurrent_calls_start_once(tmp_path):
    import asyncio

    manager = McpSessionManager(start_timeout=20)
    results = await asyncio.gather(
        manager.toolsets_for("s1", [_binding()], str(tmp_path)),
        manager.toolsets_for("s1", [_binding()], str(tmp_path)),
    )

    assert len(results[0].toolsets) == 1
    assert results[0].toolsets[0] is results[1].toolsets[0]
    assert len(manager._entries["s1"].toolsets) == 1

    await manager.close_session("s1")


async def test_close_session_is_idempotent(tmp_path):
    manager = McpSessionManager(start_timeout=20)
    await manager.toolsets_for("s1", [_binding()], str(tmp_path))
    await manager.close_session("s1")
    await manager.close_session("s1")
    assert "s1" not in manager._entries


async def test_start_failure_warns_and_continues(tmp_path):
    manager = McpSessionManager(start_timeout=5)
    bindings = [
        McpToolBinding(id="broken", command="definitely-not-a-real-command-xyz"),
        _binding("echo"),
    ]
    result = await manager.toolsets_for("s1", bindings, str(tmp_path))

    assert len(result.toolsets) == 1
    assert [w.server_id for w in result.warnings] == ["broken"]

    await manager.close_session("s1")


async def test_env_values_are_not_logged(tmp_path):
    from loguru import logger

    messages: list[str] = []
    sink = logger.add(lambda message: messages.append(str(message)), level="DEBUG")
    try:
        manager = McpSessionManager(start_timeout=20)
        binding = McpToolBinding(
            id="echo",
            command=sys.executable,
            args=[str(SERVER)],
            env={"SUPER_SECRET": "do-not-log-me"},
        )
        await manager.toolsets_for("s1", [binding], str(tmp_path))
        await manager.close_session("s1")
    finally:
        logger.remove(sink)

    assert all("do-not-log-me" not in message for message in messages)

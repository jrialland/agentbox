import asyncio
import shutil

import pytest

from agentbox_harness.spec import McpToolBinding
from agentbox_harness.tools.mcp_session import McpSessionManager


@pytest.mark.timeout(120)
async def test_uvx_mcp_server_time_lifecycle(tmp_path):
    if shutil.which("uvx") is None:
        pytest.skip("uvx is not installed")

    manager = McpSessionManager(start_timeout=90)
    binding = McpToolBinding(
        id="time",
        command="uvx",
        args=["mcp-server-time"],
        cwd="",
    )
    try:
        result = await manager.toolsets_for("s1", [binding], str(tmp_path))
        if result.warnings:
            pytest.skip(f"uvx mcp-server-time unavailable: {result.warnings[0].message}")
        assert len(result.toolsets) == 1
        toolset = result.toolsets[0]

        tools = await asyncio.wait_for(toolset.list_tools(), timeout=30)
        names = {tool.name for tool in tools}
        assert any(name.endswith("get_current_time") for name in names)

        current = await asyncio.wait_for(
            toolset.call_tool_for_app(
                next(name for name in names if name.endswith("get_current_time")),
                {"timezone": "UTC"},
            ),
            timeout=30,
        )
        assert current

        again = await manager.toolsets_for("s1", [binding], str(tmp_path))
        assert again.toolsets[0] is toolset
        assert len(manager._entries["s1"].toolsets) == 1
    finally:
        await manager.close_session("s1")
    assert "s1" not in manager._entries

"""Shared fixtures: a real (HTTP) MCP test server for MCP Apps tests."""

from __future__ import annotations

import socket
import threading
import time

import pytest
import pytest_asyncio
import uvicorn
from mcp_app_server import build_server

from agentbox_api.subagent_sessions import (
    get_subagent_session_manager,
    reset_subagent_session_manager,
)
from agentbox_harness.tools.mcp_session import (
    get_mcp_session_manager,
    reset_mcp_session_manager,
)


@pytest_asyncio.fixture(autouse=True)
async def _reset_mcp_session_manager():
    reset_mcp_session_manager()
    yield
    await get_mcp_session_manager().close_all()
    reset_mcp_session_manager()


@pytest_asyncio.fixture(autouse=True)
async def _reset_subagent_session_manager():
    reset_subagent_session_manager()
    yield
    await get_subagent_session_manager().shutdown()
    reset_subagent_session_manager()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def mcp_server_url():
    port = _free_port()
    app = build_server().streamable_http_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    thread.join(timeout=5)

"""Shared fixtures: a real (HTTP) MCP test server for MCP Apps tests."""

from __future__ import annotations

import os
import socket
import threading
import time
from functools import lru_cache

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

@lru_cache(maxsize=1)
def _docker_available() -> bool:
    if os.environ.get("AGENTBOX_SKIP_CONTAINERS") == "1":
        return False
    try:
        from testcontainers.core.docker_client import DockerClient

        return bool(DockerClient().client.ping())
    except Exception:
        return False


def _require_docker() -> None:
    if not _docker_available():
        pytest.skip("Docker unavailable for database container tests")


@pytest.fixture(scope="session")
def postgres_url():
    _require_docker()
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer(
        "postgres:16", username="agentbox", password="agentbox", dbname="agentbox"
    ) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        yield f"postgresql+asyncpg://agentbox:agentbox@{host}:{port}/agentbox"


@pytest.fixture(scope="session")
def mysql_url():
    _require_docker()
    from testcontainers.community.mysql import MySqlContainer

    with MySqlContainer(
        "mysql:8.0",
        username="agentbox",
        password="agentbox",
        dbname="agentbox",
        root_password="root",
    ) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(3306)
        yield f"mysql+aiomysql://agentbox:agentbox@{host}:{port}/agentbox"


@pytest.fixture(scope="session")
def mariadb_url():
    _require_docker()
    from testcontainers.community.mysql import MySqlContainer

    with MySqlContainer(
        "mariadb:11",
        username="agentbox",
        password="agentbox",
        dbname="agentbox",
        root_password="root",
    ) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(3306)
        yield f"mysql+aiomysql://agentbox:agentbox@{host}:{port}/agentbox"


@pytest.fixture(params=["sqlite", "postgresql", "mysql", "mariadb"])
def db_url(request):
    if request.param == "sqlite":
        return "sqlite+aiosqlite:///:memory:"
    name = "postgres_url" if request.param == "postgresql" else f"{request.param}_url"
    return request.getfixturevalue(name)

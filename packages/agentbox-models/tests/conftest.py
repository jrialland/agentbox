import os
from functools import lru_cache

import pytest


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

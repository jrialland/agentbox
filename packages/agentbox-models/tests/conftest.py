import pytest


@pytest.fixture(params=["sqlite", "postgresql", "mysql", "mariadb"])
def db_url(request):
    if request.param == "sqlite":
        return "sqlite+aiosqlite:///:memory:"
    return request.getfixturevalue(f"{request.param}_url")

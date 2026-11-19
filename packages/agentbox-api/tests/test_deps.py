import pytest
from fastapi import HTTPException
from starlette.authentication import AuthCredentials

from agentbox_api.deps import require_permission


class _User:
    def __init__(self, authenticated: bool = True):
        self.is_authenticated = authenticated


async def test_require_permission_allows():
    dep = require_permission("agents:read")

    class Req:
        auth = AuthCredentials(scopes=["agents:read"])
        user = _User()

    result = await dep(Req())  # type: ignore[arg-type]
    assert result is Req.user


async def test_require_permission_denies():
    dep = require_permission("agents:read")

    class Req:
        auth = AuthCredentials(scopes=["other"])
        user = _User()

    with pytest.raises(HTTPException) as exc:
        await dep(Req())  # type: ignore[arg-type]
    assert exc.value.status_code == 403


async def test_require_permission_unauthenticated_is_401():
    dep = require_permission("agents:read")

    class Req:
        auth = AuthCredentials(scopes=[])
        user = _User(authenticated=False)

    with pytest.raises(HTTPException) as exc:
        await dep(Req())  # type: ignore[arg-type]
    assert exc.value.status_code == 401

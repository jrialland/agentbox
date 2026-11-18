import pytest
from fastapi import HTTPException
from starlette.authentication import AuthCredentials

from agentbox_api.deps import require_permission


async def test_require_permission_allows():
    dep = require_permission("agents:read")

    class Req:
        auth = AuthCredentials(scopes=["agents:read"])
        user = "alice"

    assert await dep(Req()) == "alice"  # type: ignore[arg-type]


async def test_require_permission_denies():
    dep = require_permission("agents:read")

    class Req:
        auth = AuthCredentials(scopes=["other"])

    with pytest.raises(HTTPException) as exc:
        await dep(Req())  # type: ignore[arg-type]
    assert exc.value.status_code == 403

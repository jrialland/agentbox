from pydantic_ai.exceptions import RunCancelled

from agentbox_harness.errors import normalize_error
from agentbox_harness.tools.filesystem import PathEscapesRootError


def test_cancelled_is_cancelled():
    out = normalize_error(RunCancelled("cancelled"))
    assert out.status == "cancelled"


def test_escape_is_error():
    out = normalize_error(PathEscapesRootError("../x"))
    assert out.status == "error"
    assert "root" in out.message.lower() or "escape" in out.message.lower()


def test_unknown_is_error():
    out = normalize_error(RuntimeError("boom"))
    assert out.status == "error"
    assert out.message == "boom"

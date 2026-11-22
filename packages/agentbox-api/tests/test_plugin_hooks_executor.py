from __future__ import annotations

import pathlib
import sys

import httpx
import pytest

from agentbox_api.plugin_hook_config import (
    CommandAction,
    ContextAction,
    HttpAction,
    PluginHook,
)
from agentbox_api.plugin_hooks import (
    HookContext,
    HookExecutionError,
    HookExecutor,
)


def _command_hook(script: pathlib.Path, **kwargs) -> PluginHook:
    return PluginHook(
        id="test",
        event="run_start",
        action=CommandAction(
            type="command",
            command=sys.executable,
            args=[str(script)],
            **kwargs,
        ),
    )


def _context(**kwargs) -> HookContext:
    return HookContext(event="run_start", session_id="s1", **kwargs)


async def test_command_json_response(tmp_path):
    script = tmp_path / "hook.py"
    script.write_text(
        "import json,sys\n"
        "payload=json.load(sys.stdin)\n"
        "print(json.dumps({"
        "'decision': 'allow', "
        "'context': 'seen ' + payload['event'], "
        "'args': {'x': 1}"
        "}))\n",
        encoding="utf-8",
    )
    result = await HookExecutor().execute(
        _command_hook(script), _context(project_root=str(tmp_path))
    )
    assert result.decision == "allow"
    assert result.context == "seen run_start"
    assert result.args == {"x": 1}


async def test_command_plain_text_is_context(tmp_path):
    script = tmp_path / "hook.py"
    script.write_text("print('plain context')", encoding="utf-8")
    result = await HookExecutor().execute(
        _command_hook(script), _context(project_root=str(tmp_path))
    )
    assert result.context == "plain context"


async def test_command_nonzero_is_error(tmp_path):
    script = tmp_path / "hook.py"
    script.write_text("raise SystemExit(2)", encoding="utf-8")
    with pytest.raises(HookExecutionError, match="exited with 2"):
        await HookExecutor().execute(
            _command_hook(script), _context(project_root=str(tmp_path))
        )


async def test_command_timeout_is_error(tmp_path):
    script = tmp_path / "hook.py"
    script.write_text("import time; time.sleep(2)", encoding="utf-8")
    hook = _command_hook(script, timeout_ms=100)
    with pytest.raises(HookExecutionError, match="timed out"):
        await HookExecutor().execute(hook, _context())


async def test_command_output_cap(tmp_path):
    script = tmp_path / "hook.py"
    script.write_text("print('x' * 70000)", encoding="utf-8")
    with pytest.raises(HookExecutionError, match="exceeds limit"):
        await HookExecutor().execute(
            _command_hook(script), _context(project_root=str(tmp_path))
        )


async def test_command_env_and_cwd(tmp_path):
    script = tmp_path / "hook.py"
    script.write_text(
        "import json,os\n"
        "print(json.dumps({"
        "'context': os.environ['PLUGIN_ROOT'] + '|' + "
        "os.environ['PLUGIN_DATA'] + '|' + os.getcwd()"
        "}))\n",
        encoding="utf-8",
    )
    hook = _command_hook(script)
    result = await HookExecutor().execute(
        hook,
        _context(
            project_root=str(tmp_path),
            plugin_root=str(tmp_path / "plugin"),
            plugin_data=str(tmp_path / "data"),
        ),
    )
    assert result.context == (
        f"{tmp_path / 'plugin'}|{tmp_path / 'data'}|{tmp_path}"
    )


async def test_static_context_action():
    hook = PluginHook(
        id="note",
        event="run_start",
        action=ContextAction(type="context", text="hello"),
    )
    result = await HookExecutor().execute(hook, _context())
    assert result.context == "hello"


async def test_http_json_response(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={"context": "from http", "decision": "deny", "reason": "no"},
        )

    original = httpx.AsyncClient

    def factory(**kwargs):
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("agentbox_api.plugin_hooks.httpx.AsyncClient", factory)
    hook = PluginHook(
        id="http",
        event="before_tool",
        action=HttpAction(type="http", url="http://localhost:9/check"),
    )
    result = await HookExecutor().execute(
        hook, HookContext(event="before_tool", session_id="s1")
    )
    assert result.context == "from http"
    assert result.decision == "deny"
    assert seen["url"] == "http://localhost:9/check"
    assert b"before_tool" in seen["body"]


async def test_http_non_2xx_is_error(monkeypatch):
    original = httpx.AsyncClient

    def factory(**kwargs):
        return original(
            transport=httpx.MockTransport(lambda request: httpx.Response(500)),
            **kwargs,
        )

    monkeypatch.setattr("agentbox_api.plugin_hooks.httpx.AsyncClient", factory)
    hook = PluginHook(
        id="http",
        event="run_start",
        action=HttpAction(type="http", url="http://localhost:9/check"),
    )
    with pytest.raises(HookExecutionError, match="returned 500"):
        await HookExecutor().execute(hook, _context())


async def test_http_redirect_is_not_followed(monkeypatch):
    original = httpx.AsyncClient

    def factory(**kwargs):
        return original(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    302, headers={"Location": "http://localhost:9/next"}
                )
            ),
            **kwargs,
        )

    monkeypatch.setattr("agentbox_api.plugin_hooks.httpx.AsyncClient", factory)
    hook = PluginHook(
        id="http",
        event="run_start",
        action=HttpAction(type="http", url="http://localhost:9/check"),
    )
    with pytest.raises(HookExecutionError, match="returned 302"):
        await HookExecutor().execute(hook, _context())


async def test_http_response_cap(monkeypatch):
    original = httpx.AsyncClient

    def factory(**kwargs):
        return original(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"x" * 70000)
            ),
            **kwargs,
        )

    monkeypatch.setattr("agentbox_api.plugin_hooks.httpx.AsyncClient", factory)
    hook = PluginHook(
        id="http",
        event="run_start",
        action=HttpAction(type="http", url="http://localhost:9/check"),
    )
    with pytest.raises(HookExecutionError, match="exceeds limit"):
        await HookExecutor().execute(hook, _context())

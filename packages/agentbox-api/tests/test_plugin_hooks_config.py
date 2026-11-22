from __future__ import annotations

import json
import pathlib

from agentbox_api.plugin_catalog import PluginCatalog
from agentbox_api.plugin_hook_config import (
    CommandAction,
    ContextAction,
    HttpAction,
    PluginHook,
    load_plugin_hooks,
)

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def _plugin(
    tmp_path: pathlib.Path,
    hooks: list[dict] | None = None,
    raw: str | None = None,
) -> pathlib.Path:
    plugin = tmp_path / "user" / "acme-tools"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        json.dumps({"$schema": PLUGIN_SCHEMA, "name": "acme-tools"}),
        encoding="utf-8",
    )
    hooks_dir = plugin / "com.agentbox" / "hooks"
    hooks_dir.mkdir(parents=True)
    text = raw
    if text is None:
        text = json.dumps({"version": 1, "hooks": hooks or []})
    (hooks_dir / "hooks.json").write_text(text, encoding="utf-8")
    return plugin


def _load(tmp_path: pathlib.Path):
    catalog = PluginCatalog(str(tmp_path / "user"), str(tmp_path / "data"))
    return catalog.discover(str(tmp_path / "project"), "prj1")[0]


def test_no_hooks_file(tmp_path):
    plugin = tmp_path / "user" / "acme-tools"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        json.dumps({"$schema": PLUGIN_SCHEMA, "name": "acme-tools"}),
        encoding="utf-8",
    )
    loaded = _load(tmp_path)
    assert loaded.hooks == ()


def test_command_hook_is_normalized(tmp_path):
    _plugin(
        tmp_path,
        [
            {
                "id": "after-edit",
                "event": "after_tool",
                "tools": ["write_file", "edit_*"],
                "action": {
                    "type": "command",
                    "command": "./check.sh",
                    "args": ["${PLUGIN_ROOT}/x", "${PLUGIN_DATA}/y"],
                    "env": {"DATA": "${PLUGIN_DATA}"},
                    "cwd": "${PLUGIN_DATA}",
                    "timeout_ms": 1000,
                },
            }
        ],
    )
    loaded = _load(tmp_path)
    hook = loaded.hooks[0]
    assert hook.id == "after-edit"
    assert hook.event == "after_tool"
    assert hook.tools == ["write_file", "edit_*"]
    assert isinstance(hook.action, CommandAction)
    plugin = tmp_path / "user" / "acme-tools"
    assert hook.action.command == str(plugin / "check.sh")
    assert hook.action.args[0] == f"{plugin}/x"
    assert hook.action.env["DATA"] == str(tmp_path / "data" / "acme-tools")
    assert hook.action.cwd == str(tmp_path / "data" / "acme-tools")
    assert hook.on_error == "ignore"


def test_http_and_context_hooks(tmp_path):
    _plugin(
        tmp_path,
        [
            {
                "id": "check",
                "event": "before_tool",
                "action": {
                    "type": "http",
                    "url": "http://localhost:9999/check",
                    "headers": {"X-Test": "1"},
                    "timeout_ms": 999999,
                },
                "on_error": "deny",
            },
            {
                "id": "note",
                "event": "run_start",
                "action": {"type": "context", "text": "remember"},
            },
        ],
    )
    loaded = _load(tmp_path)
    assert len(loaded.hooks) == 2
    check, note = loaded.hooks
    assert isinstance(check.action, HttpAction)
    assert check.action.method == "POST"
    assert check.action.timeout_ms == 30_000
    assert check.on_error == "deny"
    assert isinstance(note.action, ContextAction)
    assert note.action.text == "remember"


def test_invalid_hook_is_skipped(tmp_path):
    _plugin(
        tmp_path,
        [
            {"id": "bad", "event": "after_tool", "action": {"type": "nope"}},
            {
                "id": "good",
                "event": "run_start",
                "action": {"type": "context", "text": "ok"},
            },
        ],
    )
    loaded = _load(tmp_path)
    assert [hook.id for hook in loaded.hooks] == ["good"]
    assert any(
        issue.component == "com.agentbox:hook:bad" for issue in loaded.issues
    )


def test_invalid_top_level_disables_all_hooks(tmp_path):
    _plugin(tmp_path, raw=json.dumps({"version": 2, "hooks": []}))
    loaded = _load(tmp_path)
    assert loaded.hooks == ()
    assert any(
        issue.component == "com.agentbox:hooks" for issue in loaded.issues
    )


def test_duplicate_ids_skip_second(tmp_path):
    _plugin(
        tmp_path,
        [
            {
                "id": "dup",
                "event": "run_start",
                "action": {"type": "context", "text": "one"},
            },
            {
                "id": "dup",
                "event": "run_start",
                "action": {"type": "context", "text": "two"},
            },
        ],
    )
    loaded = _load(tmp_path)
    assert [hook.id for hook in loaded.hooks] == ["dup"]
    assert isinstance(loaded.hooks[0].action, ContextAction)
    assert loaded.hooks[0].action.text == "one"


def test_tools_on_non_tool_event_is_invalid(tmp_path):
    _plugin(
        tmp_path,
        [
            {
                "id": "bad",
                "event": "run_start",
                "tools": ["write_file"],
                "action": {"type": "context", "text": "x"},
            }
        ],
    )
    assert _load(tmp_path).hooks == ()


def test_deny_on_non_before_tool_is_invalid(tmp_path):
    _plugin(
        tmp_path,
        [
            {
                "id": "bad",
                "event": "after_tool",
                "action": {"type": "context", "text": "x"},
                "on_error": "deny",
            }
        ],
    )
    assert _load(tmp_path).hooks == ()


def test_command_escape_is_rejected(tmp_path):
    _plugin(
        tmp_path,
        [
            {
                "id": "escape",
                "event": "run_start",
                "action": {"type": "command", "command": "./../evil"},
            }
        ],
    )
    loaded = _load(tmp_path)
    assert loaded.hooks == ()
    assert any(
        issue.component == "com.agentbox:hook:escape" for issue in loaded.issues
    )


def test_bad_cwd_is_rejected(tmp_path):
    _plugin(
        tmp_path,
        [
            {
                "id": "bad-cwd",
                "event": "run_start",
                "action": {
                    "type": "command",
                    "command": "python",
                    "cwd": "C:\\Windows",
                },
            }
        ],
    )
    assert _load(tmp_path).hooks == ()


def test_http_rejects_remote_plain_http(tmp_path):
    _plugin(
        tmp_path,
        [
            {
                "id": "insecure",
                "event": "run_start",
                "action": {"type": "http", "url": "http://example.com/hook"},
            }
        ],
    )
    assert _load(tmp_path).hooks == ()


def test_load_plugin_hooks_returns_issues(tmp_path):
    plugin = _plugin(tmp_path, raw="not json")
    hooks, issues = load_plugin_hooks(
        plugin, tmp_path / "data" / "acme-tools"
    )
    assert hooks == ()
    assert issues
    assert issues[0].component == "com.agentbox:hooks"


def test_hook_model_requires_known_action(tmp_path):
    hook = PluginHook.model_validate(
        {
            "id": "note",
            "event": "run_start",
            "action": {"type": "context", "text": "x"},
        }
    )
    assert hook.action.type == "context"

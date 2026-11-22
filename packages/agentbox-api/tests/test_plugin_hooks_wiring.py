from __future__ import annotations

import json

from test_plugin_skills import _setup, _write_plugin

from agentbox_api.media import MediaStore
from agentbox_api.plugin_hooks import PluginHooks
from agentbox_api.plugin_service import PluginService
from agentbox_api.runtime import delete_session_data
from agentbox_api.skills import prepare_agent


def _write_hook(plugin) -> None:
    hooks = plugin / "com.agentbox" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hooks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": [
                    {
                        "id": "note",
                        "event": "run_start",
                        "action": {"type": "context", "text": "note"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


async def _prepare(factory, project, tmp_path):
    return await prepare_agent(
        factory,
        "bot",
        str(project),
        str(tmp_path / "skills"),
        session_id="s1",
        project_id="prj",
        plugins_user_dir=str(tmp_path / "user"),
        plugins_data_dir=str(tmp_path / "data"),
    )


async def test_prepare_agent_attaches_plugin_hooks(tmp_path):
    engine, factory, project = await _setup(tmp_path)
    try:
        plugin = _write_plugin(tmp_path / "user")
        _write_hook(plugin)
        service = PluginService(
            factory, str(tmp_path / "user"), str(tmp_path / "data")
        )
        await service.set_enabled(
            "acme-tools", "global", None, True, str(project)
        )
        prepared = await _prepare(factory, project, tmp_path)
        assert isinstance(prepared.plugin_hooks, PluginHooks)
        assert prepared.plugin_hooks.refs[0].hook.id == "note"
    finally:
        await engine.dispose()


async def test_prepare_agent_without_hooks_has_none(tmp_path):
    engine, factory, project = await _setup(tmp_path)
    try:
        _write_plugin(tmp_path / "user")
        service = PluginService(
            factory, str(tmp_path / "user"), str(tmp_path / "data")
        )
        await service.set_enabled(
            "acme-tools", "global", None, True, str(project)
        )
        prepared = await _prepare(factory, project, tmp_path)
        assert prepared.plugin_hooks is None
    finally:
        await engine.dispose()


async def test_delete_session_data_runs_session_end(tmp_path, monkeypatch):
    engine, factory, _ = await _setup(tmp_path)
    calls: list[str] = []

    class FakeRuntime:
        async def end_session(self, session_id: str) -> None:
            calls.append(session_id)

    monkeypatch.setattr(
        "agentbox_api.plugin_hooks.get_plugin_hook_runtime",
        lambda: FakeRuntime(),
    )
    try:
        await delete_session_data(
            factory, "s1", MediaStore(str(tmp_path / "media"))
        )
        assert calls == ["s1"]
    finally:
        await engine.dispose()

from types import SimpleNamespace

from agentbox_api.runtime import context_editing_config_from_settings


def test_context_editing_config_from_settings():
    settings = SimpleNamespace(
        context_editing_enabled=True,
        context_editing_trigger_tokens=50_000,
        context_editing_trigger_ratio=0.75,
        context_editing_target_ratio=0.5,
        context_editing_keep_tool_results=4,
        context_editing_keep_recent_messages=8,
        context_editing_clear_tool_inputs=True,
        context_editing_clear_binary=True,
        context_editing_exclude_tools="todo_list, lsp_diagnostics",
        context_editing_placeholder="[cleared]",
        context_editing_binary_placeholder="[file omitted]",
    )
    config = context_editing_config_from_settings(settings)
    assert config.enabled is True
    assert config.trigger_tokens == 50_000
    assert config.trigger_ratio == 0.75
    assert config.target_ratio == 0.5
    assert config.keep_tool_results == 4
    assert config.keep_recent_messages == 8
    assert config.clear_tool_inputs is True
    assert config.clear_binary is True
    assert config.exclude_tools == ("todo_list", "lsp_diagnostics")
    assert config.placeholder == "[cleared]"
    assert config.binary_placeholder == "[file omitted]"


def test_context_editing_config_clamps_ratios():
    settings = SimpleNamespace(
        context_editing_enabled=False,
        context_editing_trigger_tokens=-1,
        context_editing_trigger_ratio=2.0,
        context_editing_target_ratio=0.0,
        context_editing_keep_tool_results=-2,
        context_editing_keep_recent_messages=-1,
        context_editing_clear_tool_inputs=False,
        context_editing_clear_binary=False,
        context_editing_exclude_tools="",
        context_editing_placeholder="x",
        context_editing_binary_placeholder="y",
    )
    config = context_editing_config_from_settings(settings)
    assert config.enabled is False
    assert config.trigger_tokens == 0
    assert config.trigger_ratio == 1.0
    assert config.target_ratio == 0.05
    assert config.keep_tool_results == 0
    assert config.keep_recent_messages == 0
    assert config.exclude_tools == ()

from agentbox_api.config import Settings
from agentbox_api.runtime import compaction_config_from_settings


def test_compaction_config_from_settings():
    settings = Settings(
        jwt_secret="s" * 32,
        compaction_enabled=False,
        compaction_ratio=0.7,
        compaction_keep_turns=6,
        compaction_input_budget_tokens=12_000,
        compaction_max_summary_chars=4_000,
    )
    config = compaction_config_from_settings(settings)
    assert config.enabled is False
    assert config.ratio == 0.7
    assert config.keep_turns == 6
    assert config.input_budget_tokens == 12_000
    assert config.max_summary_chars == 4_000

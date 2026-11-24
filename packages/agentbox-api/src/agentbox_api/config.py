"""Runtime settings for the API, resolved from the environment and ``agentbox.toml``.

Settings combine pydantic-settings environment loading with database and media
resolution from :mod:`agentbox_models.config`. Constructor values win, then the
process environment and ``.env``, then the optional TOML file, then built-in
defaults.
"""

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentbox_models.config import (
    load_config_file,
    resolve_database_url,
    resolve_media_dir,
)


class Settings(BaseSettings):
    """Validated API configuration.

    Each field is populated from a same-named environment variable (case
    insensitive) or the ``.env`` file. ``jwt_secret`` is required and must be at
    least 32 characters; ``jwt_expiry_seconds`` bounds how long issued tokens
    stay valid. ``database_url`` and ``media_dir`` accept explicit values; when
    left empty they are resolved in the model validator from the environment and
    ``agentbox.toml``.

    Attributes:
        jwt_secret: Secret used to sign and verify JWTs. Short secrets are
            rejected at startup to keep signed tokens non-forgeable.
        database_url: Async SQLAlchemy URL; empty means resolve from the
            database environment/TOML settings.
        media_dir: Directory for avatars, attachments, and A2A cards; empty
            means resolve from ``MEDIA_DIR`` or the TOML storage settings.
        cors_origins: Origins allowed to make credentialed cross-origin calls.
    """

    database_url: str = ""
    media_dir: str = ""
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 3600
    cors_origins: list[str] = ["http://localhost:5173"]
    a2a_workspace: str = "."
    a2a_public_url: str = "http://localhost:8000"
    skills_user_dir: str = "~/.agents/skills"
    plugins_user_dir: str = "~/.agents/plugins"
    plugins_data_dir: str = "~/.agents/plugins/data"
    media_max_dimension: int = 1568
    media_max_bytes: int = 1_500_000
    log_level: str = "INFO"
    log_dir: str = "./logs"
    log_rotation: str = "10 MB"
    log_retention: str = "14 days"
    log_compression: str = "zip"
    log_intercept: bool = True
    lsp_enabled: bool = True
    lsp_servers_json: str | None = None
    lsp_initialize_timeout: float = 10.0
    lsp_diagnostics_timeout: float = 5.0
    lsp_failure_backoff_seconds: float = 60.0
    lsp_mode: str = "auto"
    lsp_max_open_documents: int = 50
    lsp_first_change_timeout: float = 1.0
    lsp_settle_window: float = 0.3
    lsp_session_snapshot_limit: int = 100
    lsp_warm_on_start: bool = False
    web_search_provider: str = "auto"
    web_search_timeout: float = 10.0
    web_search_max_results: int = 5
    web_search_region: str = "us-en"
    web_search_safesearch: str = "moderate"
    web_search_ddgs_backend: str = "auto"
    searxng_url: str | None = None
    web_fetch_timeout: float = 15.0
    web_fetch_max_chars: int = 40_000
    web_fetch_max_bytes: int = 2_000_000
    web_fetch_user_agent: str = "agentbox/0.1"
    compaction_enabled: bool = True
    compaction_ratio: float = 0.8
    compaction_keep_turns: int = 4
    compaction_input_budget_tokens: int = 16_000
    compaction_max_summary_chars: int = 8_000
    context_editing_enabled: bool = True
    context_editing_trigger_tokens: int = 100_000
    context_editing_trigger_ratio: float = 0.8
    context_editing_target_ratio: float = 0.6
    context_editing_keep_tool_results: int = 3
    context_editing_keep_recent_messages: int = 6
    context_editing_clear_tool_inputs: bool = False
    context_editing_clear_binary: bool = True
    context_editing_exclude_tools: str = ""
    context_editing_placeholder: str = (
        "[tool result cleared to save context; re-run the tool if needed]"
    )
    context_editing_binary_placeholder: str = (
        "[attachment omitted to save context]"
    )
    mcp_idle_ttl_seconds: float = 1800
    mcp_start_timeout_seconds: float = 30
    mcp_sweep_interval_seconds: float = 60

    model_config = SettingsConfigDict(env_file=".env")

    @model_validator(mode="after")
    def _resolve_paths(self):
        # Precedence for the resolved fields: explicit constructor/env value,
        # then DATABASE_URL/MEDIA_DIR, then agentbox.toml, then defaults. The
        # config file is only consulted when the field is still empty.
        config = load_config_file()
        if not self.database_url:
            self.database_url = resolve_database_url(config)
        if not self.media_dir:
            self.media_dir = resolve_media_dir(config)
        return self

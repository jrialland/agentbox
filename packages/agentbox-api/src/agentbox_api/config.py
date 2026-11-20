from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./agentbox.db"
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 3600
    cors_origins: list[str] = ["http://localhost:5173"]
    a2a_workspace: str = "."
    a2a_public_url: str = "http://localhost:8000"
    skills_user_dir: str = "~/.agents/skills"
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

    model_config = SettingsConfigDict(env_file=".env")

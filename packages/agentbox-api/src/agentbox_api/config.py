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

    model_config = SettingsConfigDict(env_file=".env")

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./agentbox.db"
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 3600

    model_config = SettingsConfigDict(env_file=".env")

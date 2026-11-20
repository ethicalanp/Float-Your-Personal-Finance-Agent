from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEV_JWT_SECRET = "dev-insecure-secret-key-change-in-production-min32bytes"


class Settings(BaseSettings):
    """Central application configuration. Every variable uses the PFA_ prefix."""

    model_config = SettingsConfigDict(
        env_prefix="PFA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Personal Finance Agent"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False

    api_v1_prefix: str = "/api/v1"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # PostgreSQL connection URL; using psycopg 3 (postgresql+psycopg://).
    database_url: str | None = None

    # Security & JWT configuration
    jwt_secret_key: str = INSECURE_DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30  # 15 to 30 minutes for security
    borrow_model_path: str | None = None

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are switched off in production."""
        return self.app_env != "production"

    @model_validator(mode="after")
    def _validate_production_rules(self) -> Self:
        if self.app_env == "production":
            if self.debug:
                raise ValueError("debug must be false when app_env is production")
            if (
                not self.jwt_secret_key
                or self.jwt_secret_key == INSECURE_DEV_JWT_SECRET
                or len(self.jwt_secret_key) < 32
            ):
                raise ValueError(
                    "PFA_JWT_SECRET_KEY must be a cryptographically strong secret (min 32 chars) in production"
                )
            if not self.database_url:
                raise ValueError("PFA_DATABASE_URL must be configured when app_env is production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()

from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are switched off in production."""
        return self.app_env != "production"

    @model_validator(mode="after")
    def _no_debug_in_production(self) -> Self:
        if self.app_env == "production" and self.debug:
            raise ValueError("debug must be false when app_env is production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()

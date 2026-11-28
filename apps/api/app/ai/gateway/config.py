import logging
import os
from pathlib import Path

from pydantic import BaseModel, SecretStr, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

logger = logging.getLogger("app.ai.gateway.config")


def _read_env_file_key(key: str) -> str | None:
    """Read a single key from local .env files when not exported to os.environ."""
    for candidate in (Path(".env"), Path("apps/api/.env")):
        if not candidate.is_file():
            continue
        try:
            for raw_line in candidate.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    val = v.strip().strip("'\"")
                    if val:
                        return val
        except OSError:
            continue
    return None


class FallbackLLMConfig(BaseModel):
    provider: str = ""
    base_url: str = ""
    api_key: SecretStr | None = None
    model: str = ""
    approved_for_real_data: bool = False

    def __repr__(self) -> str:
        return (
            f"FallbackLLMConfig(provider='{self.provider}', model='{self.model}', "
            f"base_url='{self.base_url}', approved_for_real_data={self.approved_for_real_data})"
        )

    def __str__(self) -> str:
        return self.__repr__()


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PFA_LLM_",
        env_nested_delimiter="__",
        env_file=(".env", "apps/api/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        if os.getenv("PFA_APP_ENV", "").lower() == "test":
            return (init_settings, env_settings, file_secret_settings)
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)

    provider: str = "fake"
    base_url: str = ""
    api_key: SecretStr | None = None
    model: str = "fake-model"
    timeout_seconds: float = 15.0
    overall_budget_seconds: float = 30.0
    max_concurrency: int = 10
    max_retries: int = 3
    daily_token_budget_per_user: int = 100_000
    request_token_budget: int = 4_000
    approved_for_real_data: bool = False
    region: str = "ap-south-1"
    data_retention_note: str = "Zero retention policy or masked real data"
    allow_cross_provider_fallback: bool = False

    fallback: FallbackLLMConfig | None = None

    @model_validator(mode="after")
    def populate_defaults_and_groq_fallback(self) -> "LLMConfig":
        # Fallback to GROQ_API_KEY from environment if provider is groq and api_key not explicitly set
        if self.provider.lower() == "groq":
            if not self.base_url:
                self.base_url = os.getenv("PFA_LLM_BASE_URL", "https://api.groq.com/openai/v1")
            if not self.model or self.model == "fake-model":
                self.model = os.getenv("PFA_LLM_MODEL", "openai/gpt-oss-120b")
            if self.api_key is None:
                groq_key = os.getenv("GROQ_API_KEY") or os.getenv("PFA_LLM_API_KEY")
                if not groq_key and os.getenv("PFA_APP_ENV", "").lower() != "test":
                    groq_key = _read_env_file_key("GROQ_API_KEY") or _read_env_file_key("PFA_LLM_API_KEY")
                if groq_key:
                    clean_key = groq_key.strip().strip("'\"")
                    self.api_key = SecretStr(clean_key)
            # Free tier concurrency & timeout safety for 120B / 70B class models
            if self.max_concurrency > 2:
                self.max_concurrency = int(os.getenv("PFA_LLM_MAX_CONCURRENCY", "2"))
            if self.timeout_seconds < 45.0:
                self.timeout_seconds = float(os.getenv("PFA_LLM_TIMEOUT_SECONDS", "60.0"))
            if self.overall_budget_seconds < 60.0:
                self.overall_budget_seconds = float(os.getenv("PFA_LLM_OVERALL_BUDGET_SECONDS", "90.0"))
            self.approved_for_real_data = True

        # In production mode with approved_for_real_data=False, log a clear warning
        app_env = os.getenv("APP_ENV", "development").lower()
        if app_env == "production" and not self.approved_for_real_data:
            logger.warning(
                "SECURITY WARNING: LLM provider '%s' is NOT approved for real customer data. "
                "All real data requests will be refused.",
                self.provider,
            )

        return self

    def is_provider_approved(self, data_class: str) -> bool:
        """Check if provider is approved for given data class."""
        if data_class == "demo":
            return True
        return self.approved_for_real_data

    def __repr__(self) -> str:
        return (
            f"LLMConfig(provider='{self.provider}', model='{self.model}', "
            f"base_url='{self.base_url}', approved_for_real_data={self.approved_for_real_data}, "
            f"timeout_seconds={self.timeout_seconds}, max_retries={self.max_retries})"
        )

    def __str__(self) -> str:
        return self.__repr__()

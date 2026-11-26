import os
from functools import lru_cache
from typing import Any, Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEV_JWT_SECRET = "dev-insecure-secret-key-change-in-production-min32bytes"


class Settings(BaseSettings):
    """Central application configuration. Every variable uses the PFA_ prefix."""

    model_config = SettingsConfigDict(
        env_prefix="PFA_",
        env_file=(".env", "apps/api/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Personal Finance Agent"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False

    api_v1_prefix: str = "/api/v1"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Database URL. In production, PostgreSQL with psycopg 3 is strictly required.
    # In local development, falls back to local SQLite if PFA_DATABASE_URL is unset.
    database_url: str = "sqlite+aiosqlite:///dev.db"

    # Security & JWT configuration
    jwt_secret_key: str = INSECURE_DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30  # 15 to 30 minutes for security
    jwt_refresh_token_expire_days: int = 30
    password_reset_token_expire_minutes: int = 15
    email_verification_token_expire_hours: int = 24
    internal_metrics_token: SecretStr | None = None
    borrow_model_path: str | None = None
    enable_synthetic_ml_demos: bool = False
    synthetic_borrow_demo_model_path: str | None = None
    synthetic_scam_demo_model_path: str | None = None

    # Google OAuth configuration
    google_client_id: str | None = None
    google_client_ids: str = ""

    # SMS & OTP configuration
    sms_provider: Literal["fake", "msg91", "aws_sns"] = "fake"
    sms_country_allowlist: str = "+91"
    msg91_auth_key: SecretStr | None = None
    msg91_template_id: str | None = None
    msg91_sender_id: str | None = None
    sms_daily_cap: int = 1000
    otp_expiry_seconds: int = 300
    otp_cooldown_seconds: int = 60
    otp_max_attempts: int = 5
    otp_rate_limit_per_phone_hour: int = 5
    otp_rate_limit_per_ip_hour: int = 20
    otp_daily_global_cap: int = 1000

    # Admin Panel (SQLAdmin) configuration
    admin_enabled: bool = False
    admin_allowed_ips: str = "127.0.0.1,::1"
    admin_session_secret_key: SecretStr | None = None
    admin_session_expire_seconds: int = 1800  # 30 minutes default

    @field_validator("admin_enabled", "debug", "enable_synthetic_ml_demos", mode="before")
    @classmethod
    def _strip_bool_strings(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean in ("true", "1", "yes", "t", "on"):
                return True
            if v_clean in ("false", "0", "no", "f", "off", ""):
                return False
        return v

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are switched off in production."""
        return self.app_env != "production"

    @model_validator(mode="after")
    def _validate_production_rules(self) -> Self:
        if self.sms_provider == "msg91" and self.app_env != "development":
            if (
                not self.msg91_auth_key
                or not self.msg91_auth_key.get_secret_value().strip()
                or not self.msg91_template_id
                or not self.msg91_sender_id
            ):
                raise ValueError(
                    "PFA_MSG91_AUTH_KEY, PFA_MSG91_TEMPLATE_ID, and PFA_MSG91_SENDER_ID must be configured "
                    "when PFA_SMS_PROVIDER=msg91 in non-development environments."
                )

        if self.app_env == "production":
            if self.debug:
                raise ValueError("debug must be false when app_env is production")
            if self.enable_synthetic_ml_demos:
                raise ValueError("synthetic ML demos must remain disabled in production")
            if (
                not self.jwt_secret_key
                or self.jwt_secret_key == INSECURE_DEV_JWT_SECRET
                or len(self.jwt_secret_key) < 32
            ):
                raise ValueError(
                    "PFA_JWT_SECRET_KEY must be a cryptographically strong secret (min 32 chars) in production"
                )
            if not self.database_url or "sqlite" in self.database_url:
                raise ValueError(
                    "PFA_DATABASE_URL must be configured with a PostgreSQL URL (postgresql+psycopg://) in production"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance (ignoring local .env files during tests)."""
    if os.getenv("PFA_APP_ENV") == "test":
        return Settings(_env_file=None)  # type: ignore[call-arg]
    return Settings()

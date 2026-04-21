import math
from collections import Counter

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False, extra="ignore")

    env: str = Field("dev", alias="ENV")

    database_url: str = Field(..., alias="DATABASE_URL")
    session_secret: str = Field(..., alias="SESSION_SECRET")
    cookie_name: str = Field("chronos_session", alias="COOKIE_NAME")
    cookie_secure: bool = Field(True, alias="COOKIE_SECURE")
    cookie_samesite: str = Field("lax", alias="COOKIE_SAMESITE")
    session_max_age_seconds: int = Field(60 * 60 * 8, alias="SESSION_MAX_AGE_SECONDS")
    session_idle_timeout_seconds: int = Field(60 * 30, alias="SESSION_IDLE_TIMEOUT_SECONDS")
    log_level: str = Field("info", alias="LOG_LEVEL")

    smtp_enabled: bool = Field(False, alias="SMTP_ENABLED")
    smtp_host: str = Field("localhost", alias="SMTP_HOST")
    smtp_port: int = Field(25, alias="SMTP_PORT")
    smtp_username: str | None = Field(None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(None, alias="SMTP_PASSWORD")
    smtp_from: str = Field("chronos@localhost", alias="SMTP_FROM")
    smtp_use_tls: bool = Field(False, alias="SMTP_USE_TLS")

    public_url: str = Field("http://localhost", alias="PUBLIC_URL")

    auth_max_failed_attempts: int = Field(5, alias="AUTH_MAX_FAILED_ATTEMPTS")
    auth_lockout_seconds: int = Field(900, alias="AUTH_LOCKOUT_SECONDS")

    @field_validator("session_secret")
    @classmethod
    def _validate_session_secret(cls, value: str, info) -> str:
        env = (info.data.get("env") or "dev").lower()
        if env == "dev":
            return value
        if len(value) < 48:
            raise ValueError(
                f"SESSION_SECRET too short for ENV={env}: need >=48 chars, got {len(value)}. "
                "Generate via: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if _shannon_entropy(value) < 4.0:
            raise ValueError(
                f"SESSION_SECRET entropy too low for ENV={env}: need Shannon entropy >=4.0 bits/char. "
                "Generate via: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return value


settings = Settings()

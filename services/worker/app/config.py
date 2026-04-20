from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    database_url: str = Field(..., alias="DATABASE_URL")
    job_poll_interval_seconds: float = Field(5.0, alias="JOB_POLL_INTERVAL_SECONDS")
    log_level: str = Field("info", alias="LOG_LEVEL")


settings = Settings()

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")

    database_url: str = Field(alias="DATABASE_URL")
    database_url_sync: str = Field(alias="DATABASE_URL_SYNC")

    redis_url: str = Field(alias="REDIS_URL")
    redis_fsm_url: str = Field(alias="REDIS_FSM_URL")
    redis_cache_url: str = Field(alias="REDIS_CACHE_URL")

    celery_broker_url: str = Field(alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(alias="CELERY_RESULT_BACKEND")

    daily_question_limit: int = Field(default=50, alias="DAILY_QUESTION_LIMIT")
    session_timeout_seconds: int = Field(default=3600, alias="SESSION_TIMEOUT_SECONDS")
    daily_reminder_hour_utc: int = Field(default=9, alias="DAILY_REMINDER_HOUR_UTC")
    ranking_refresh_minutes: int = Field(default=15, alias="RANKING_REFRESH_MINUTES")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

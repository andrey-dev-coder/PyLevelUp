from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _to_async_pg(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


def _to_sync_pg(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg2://" + url[len("postgresql+asyncpg://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def _redis_with_db(url: str, db_index: int) -> str:
    base, _, query = url.partition("?")
    if "/" in base.split("//", 1)[-1]:
        scheme_host, _, _ = base.rpartition("/")
        new_base = f"{scheme_host}/{db_index}"
    else:
        new_base = f"{base}/{db_index}"
    return f"{new_base}?{query}" if query else new_base


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")

    database_url: str = Field(alias="DATABASE_URL")
    database_url_sync: str | None = Field(default=None, alias="DATABASE_URL_SYNC")

    redis_url: str = Field(alias="REDIS_URL")
    redis_fsm_url: str | None = Field(default=None, alias="REDIS_FSM_URL")
    redis_cache_url: str | None = Field(default=None, alias="REDIS_CACHE_URL")

    celery_broker_url: str | None = Field(default=None, alias="CELERY_BROKER_URL")
    celery_result_backend: str | None = Field(default=None, alias="CELERY_RESULT_BACKEND")

    daily_question_limit: int = Field(default=50, alias="DAILY_QUESTION_LIMIT")
    session_timeout_seconds: int = Field(default=3600, alias="SESSION_TIMEOUT_SECONDS")
    daily_reminder_hour_utc: int = Field(default=9, alias="DAILY_REMINDER_HOUR_UTC")
    ranking_refresh_minutes: int = Field(default=15, alias="RANKING_REFRESH_MINUTES")

    owner_telegram_id: int = Field(default=896090535, alias="OWNER_TELEGRAM_ID")
    default_access_code: str = Field(default="pylevelup_2026", alias="DEFAULT_ACCESS_CODE")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @model_validator(mode="after")
    def _normalize_urls(self) -> "Settings":
        self.database_url = _to_async_pg(self.database_url)
        if not self.database_url_sync:
            self.database_url_sync = _to_sync_pg(self.database_url)
        else:
            self.database_url_sync = _to_sync_pg(self.database_url_sync)
        if not self.redis_fsm_url:
            self.redis_fsm_url = _redis_with_db(self.redis_url, 1)
        if not self.redis_cache_url:
            self.redis_cache_url = _redis_with_db(self.redis_url, 2)
        if not self.celery_broker_url:
            self.celery_broker_url = _redis_with_db(self.redis_url, 3)
        if not self.celery_result_backend:
            self.celery_result_backend = _redis_with_db(self.redis_url, 4)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

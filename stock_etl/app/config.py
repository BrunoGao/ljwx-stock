from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    database_url: str = Field(alias="DATABASE_URL")
    run_mode: Literal["backfill", "daily", "reconcile"] = Field(
        default="daily", alias="RUN_MODE"
    )
    adjust: Literal["none", "qfq", "hfq"] = Field(default="qfq", alias="ADJUST")
    trading_days: int = Field(default=1200, alias="TRADING_DAYS")
    daily_lookback_calendar_days: int = Field(
        default=7, alias="DAILY_LOOKBACK_CALENDAR_DAYS"
    )
    reconcile_lookback_calendar_days: int = Field(
        default=100, alias="RECONCILE_LOOKBACK_CALENDAR_DAYS"
    )
    symbol_limit: int = Field(default=0, alias="SYMBOL_LIMIT")
    batch_size: int = Field(default=2000, alias="BATCH_SIZE")
    request_sleep_ms: int = Field(default=30, alias="REQUEST_SLEEP_MS")
    request_retries: int = Field(default=2, alias="REQUEST_RETRIES")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

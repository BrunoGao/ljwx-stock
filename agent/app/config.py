from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
import os
from pathlib import Path
import re

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_KV_PATTERN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")
_ENV_JSON_PATTERN = re.compile(r'^\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*"(.*)"\s*,?\s*$')


def _strip_wrapping_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _load_local_env_file() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env_file = repo_root / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == "" or line.startswith("#"):
            continue

        kv_match = _ENV_KV_PATTERN.match(line)
        if kv_match is not None:
            key = kv_match.group(1)
            value = _strip_wrapping_quotes(kv_match.group(2))
            os.environ.setdefault(key, value)
            continue

        json_match = _ENV_JSON_PATTERN.match(line)
        if json_match is not None:
            key = json_match.group(1)
            value = _strip_wrapping_quotes(json_match.group(2))
            os.environ.setdefault(key, value)


_load_local_env_file()


class Settings(BaseSettings):
    database_url: str = Field(alias="DATABASE_URL")
    api_key: str = Field(alias="API_KEY")
    rate_limit_rpm: int = Field(default=30, alias="RATE_LIMIT_RPM")
    max_tokens_per_run: int = Field(default=50000, alias="MAX_TOKENS_PER_RUN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    db_pool_min_size: int = Field(default=1, alias="DB_POOL_MIN_SIZE")
    db_pool_max_size: int = Field(default=10, alias="DB_POOL_MAX_SIZE")
    db_pool_timeout_seconds: float = Field(default=5.0, alias="DB_POOL_TIMEOUT_SECONDS")
    db_command_timeout_seconds: float = Field(
        default=5.0, alias="DB_COMMAND_TIMEOUT_SECONDS"
    )
    kline_query_timeout_seconds: float = Field(
        default=5.0, alias="KLINE_QUERY_TIMEOUT_SECONDS"
    )
    kline_default_limit: int = Field(default=60, alias="KLINE_DEFAULT_LIMIT")
    kline_max_limit: int = Field(default=500, alias="KLINE_MAX_LIMIT")
    kline_bulk_per_symbol_limit: int = Field(
        default=60, alias="KLINE_BULK_PER_SYMBOL_LIMIT"
    )
    kline_bulk_max_symbols: int = Field(default=500, alias="KLINE_BULK_MAX_SYMBOLS")
    kline_bulk_max_rows: int = Field(default=20000, alias="KLINE_BULK_MAX_ROWS")
    candidate_pool_size: int = Field(default=300, alias="CANDIDATE_POOL_SIZE")
    display_top_n: int = Field(default=20, alias="DISPLAY_TOP_N")
    min_amount_avg: Decimal = Field(default=Decimal("10000000"), alias="MIN_AMOUNT_AVG")
    lookback_days_calendar: int = Field(default=150, alias="LOOKBACK_DAYS_CALENDAR")
    write_reco: bool = Field(default=True, alias="WRITE_RECO")
    code_version: str = Field(default="unknown", alias="CODE_VERSION")

    llm_provider: str = Field(default="claude", alias="LLM_PROVIDER")
    anthropic_auth_token: str | None = Field(default=None, alias="ANTHROPIC_AUTH_TOKEN")
    anthropic_base_url: str = Field(
        default="https://api.anthropic.com", alias="ANTHROPIC_BASE_URL"
    )
    anthropic_model: str = Field(
        default="claude-sonnet-4-6-20260217",
        alias="ANTHROPIC_MODEL",
    )
    llm_timeout_seconds: float = Field(default=20.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_output_tokens: int = Field(default=1200, alias="LLM_MAX_OUTPUT_TOKENS")
    max_user_query_len: int = Field(default=2000, alias="MAX_USER_QUERY_LEN")

    metrics_enabled: bool = Field(default=True, alias="METRICS_ENABLED")
    qc_enabled: bool = Field(default=True, alias="QC_ENABLED")
    qc_lookback_days: int = Field(default=20, alias="QC_LOOKBACK_DAYS")
    qc_cold_start_min: int = Field(default=5, alias="QC_COLD_START_MIN")
    qc_overlap_error_threshold: Decimal = Field(
        default=Decimal("1.0"),
        alias="QC_OVERLAP_ERROR_THRESHOLD",
    )
    qc_overlap_warn_threshold: Decimal = Field(
        default=Decimal("0.9"),
        alias="QC_OVERLAP_WARN_THRESHOLD",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(alias="DATABASE_URL")

    minio_endpoint: str = Field(
        default="http://minio.infra.svc.cluster.local:9000", alias="MINIO_ENDPOINT"
    )
    minio_bucket: str = Field(default="ljwx-qlib", alias="MINIO_BUCKET")
    minio_access_key: str = Field(alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(alias="MINIO_SECRET_KEY")

    qlib_region: str = Field(default="cn", alias="QLIB_REGION")
    output_root: str = Field(default="/work/out", alias="OUTPUT_ROOT")
    model_name: str = Field(default="qlib_lightgbm_alpha158", alias="MODEL_NAME")

    horizon_days: int = Field(default=5, ge=1, alias="HORIZON_DAYS")
    train_end_date: str | None = Field(default=None, alias="TRAIN_END_DATE")
    lookback_years: int = Field(default=8, ge=1, alias="LOOKBACK_YEARS")
    export_lookback_calendar_days: int = Field(
        default=4500, ge=365, alias="EXPORT_LOOKBACK_CALENDAR_DAYS"
    )

    code_version: str = Field(default="unknown", alias="CODE_VERSION")
    dry_run: bool = Field(default=False, alias="DRY_RUN")

    model_config = SettingsConfigDict(
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(alias="DATABASE_URL")
    qlib_provider_uri: str = Field(default="/data/qlib/qlib_data/cn", alias="QLIB_PROVIDER_URI")
    qlib_model_root: str = Field(default="/data/qlib/artifacts/models", alias="QLIB_MODEL_ROOT")
    qlib_model_date: str | None = Field(default=None, alias="QLIB_MODEL_DATE")
    predict_date: str | None = Field(default=None, alias="PREDICT_DATE")
    candidate_pool_size: int = Field(default=300, ge=1, alias="CANDIDATE_POOL_SIZE")
    code_version: str = Field(default="unknown", alias="CODE_VERSION")

    model_config = SettingsConfigDict(
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

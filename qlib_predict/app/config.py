from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(alias="DATABASE_URL")
    qlib_provider_uri: str | None = Field(default=None, alias="QLIB_PROVIDER_URI")
    qlib_model_root: str | None = Field(default=None, alias="QLIB_MODEL_ROOT")
    model_dir: str = Field(default="/data/qlib/models", alias="MODEL_DIR")
    qlib_data_dir: str = Field(default="/data/qlib/data", alias="QLIB_DATA_DIR")
    qlib_model_date: str | None = Field(default=None, alias="QLIB_MODEL_DATE")
    predict_date: str | None = Field(default=None, alias="PREDICT_DATE")
    predict_trade_date: str | None = Field(default=None, alias="PREDICT_TRADE_DATE")
    candidate_pool_size: int = Field(default=300, ge=1, alias="CANDIDATE_POOL_SIZE")
    code_version: str = Field(default="unknown", alias="CODE_VERSION")

    model_config = SettingsConfigDict(
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    @property
    def resolved_provider_uri(self) -> str:
        if self.qlib_provider_uri is not None and self.qlib_provider_uri.strip() != "":
            return self.qlib_provider_uri
        return self.qlib_data_dir

    @property
    def resolved_model_root(self) -> str:
        if self.qlib_model_root is not None and self.qlib_model_root.strip() != "":
            return self.qlib_model_root
        return self.model_dir

    @property
    def resolved_predict_date(self) -> str | None:
        if self.predict_date is not None and self.predict_date.strip() != "":
            return self.predict_date
        if (
            self.predict_trade_date is not None
            and self.predict_trade_date.strip() != ""
        ):
            return self.predict_trade_date
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

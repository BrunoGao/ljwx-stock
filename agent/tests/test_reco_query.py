# ruff: noqa: E402

import asyncio
from datetime import date
import importlib
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.tools import reco_query as reco_query_module
from app.tools.reco_query import RecoQueryParams, reco_query_handler


@pytest.fixture(autouse=True)
def _prepare_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/ljwx-stock"
    )
    monkeypatch.setenv("API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_reco_query_default_date(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_value(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> object:
        assert "max(trade_date)" in query
        assert params == ("qlib_lightgbm_v1",)
        assert timeout_seconds > 0
        return date(2024, 3, 4)

    async def fake_fetch_rows(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> list[dict[str, object]]:
        assert "ORDER BY score DESC NULLS LAST" in query
        assert params[0] == date(2024, 3, 4)
        assert params[1] == "qlib_lightgbm_v1"
        assert params[2] == 20
        assert timeout_seconds > 0
        return [
            {
                "symbol": "600519",
                "score": 1.23,
                "confidence": 0.88,
                "rank": 1,
                "reason_json": {"model": "qlib"},
                "data_cutoff": date(2024, 3, 4),
                "code_version": "p3b",
            },
            {
                "symbol": "000001",
                "score": 1.11,
                "confidence": 0.77,
                "rank": 2,
                "reason_json": {"model": "qlib"},
                "data_cutoff": date(2024, 3, 4),
                "code_version": "p3b",
            },
            {
                "symbol": "300750",
                "score": 0.98,
                "confidence": 0.66,
                "rank": 3,
                "reason_json": {"model": "qlib"},
                "data_cutoff": date(2024, 3, 4),
                "code_version": "p3b",
            },
        ]

    monkeypatch.setattr(reco_query_module.db, "fetch_value", fake_fetch_value)
    monkeypatch.setattr(reco_query_module.db, "fetch_rows", fake_fetch_rows)

    result = asyncio.run(reco_query_handler(RecoQueryParams()))

    assert result.success is True
    assert result.result["trade_date"] == "2024-03-04"
    assert result.result["strategy_name"] == "qlib_lightgbm_v1"
    assert result.result["row_count"] == 3


def test_reco_query_top_n_cap() -> None:
    params = RecoQueryParams(top_n=100)
    assert params.top_n == 50


def test_reco_query_no_qlib_import() -> None:
    sys.modules.pop("qlib", None)
    module = importlib.reload(reco_query_module)

    assert hasattr(module, "reco_query_handler")
    assert "qlib" not in sys.modules

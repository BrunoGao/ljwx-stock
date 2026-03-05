# ruff: noqa: E402

import asyncio
from datetime import date
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.tools import query_kline as query_kline_module
from app.tools.query_kline import QueryKlineParams, query_kline_handler


@pytest.fixture(autouse=True)
def _prepare_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/ljwx-stock"
    )
    monkeypatch.setenv("API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_query_kline_invalid_field_raises() -> None:
    params = QueryKlineParams(symbol="600519", fields=["bad_field"], limit=10)

    with pytest.raises(ValueError, match="not in allowed fields"):
        asyncio.run(query_kline_handler(params))


def test_query_kline_fields_empty_uses_default_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_rows(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> list[dict[str, object]]:
        assert "k.adjust = $2" in query
        assert params[1] == "qfq"
        assert timeout_seconds > 0
        return [
            {
                "symbol": "600519",
                "trade_date": date(2024, 1, 2),
                "adjust": "qfq",
                "open": 10.0,
                "high": 11.0,
                "low": 9.8,
                "close": 10.5,
                "volume": 1000.0,
                "amount": 2000.0,
                "turnover": 1.2,
                "pct_chg": 0.5,
            }
        ]

    monkeypatch.setattr(query_kline_module.db, "fetch_rows", fake_fetch_rows)

    params = QueryKlineParams(symbol="600519", fields=[], adjust="qfq", limit=10)
    result = asyncio.run(query_kline_handler(params))

    assert result.success is True
    rows = result.result.get("rows")
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert "close" in rows[0]


def test_query_kline_uses_latest_window_and_returns_chronological_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_rows(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> list[dict[str, object]]:
        assert "ORDER BY k.trade_date DESC" in query
        assert params[0] == "000505"
        assert timeout_seconds > 0
        return [
            {
                "symbol": "000505",
                "trade_date": date(2026, 3, 5),
                "adjust": "qfq",
                "close": 7.23,
            },
            {
                "symbol": "000505",
                "trade_date": date(2026, 3, 4),
                "adjust": "qfq",
                "close": 7.12,
            },
        ]

    monkeypatch.setattr(query_kline_module.db, "fetch_rows", fake_fetch_rows)

    result = asyncio.run(
        query_kline_handler(
            QueryKlineParams(symbol="000505", fields=["close"], limit=2)
        )
    )
    rows = result.result.get("rows")
    assert isinstance(rows, list)
    assert rows[0]["trade_date"] == "2026-03-04"
    assert rows[1]["trade_date"] == "2026-03-05"

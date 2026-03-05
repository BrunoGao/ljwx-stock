# ruff: noqa: E402

import asyncio
from datetime import date, timedelta
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.tools import query_kline as query_kline_module
from app.tools.query_kline import QueryKlineBulkParams, query_kline_bulk_handler


@pytest.fixture(autouse=True)
def _prepare_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/ljwx-stock"
    )
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("KLINE_BULK_MAX_SYMBOLS", "500")
    monkeypatch.setenv("KLINE_BULK_MAX_ROWS", "20000")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_query_kline_bulk_invalid_field_raises() -> None:
    params = QueryKlineBulkParams(symbols=["600519"], fields=["hacker"])

    with pytest.raises(ValueError, match="not in allowed fields"):
        asyncio.run(query_kline_bulk_handler(params))


def test_query_kline_bulk_symbols_none_or_empty_means_all_market(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_queries: list[str] = []

    async def fake_fetch_value(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> object:
        assert timeout_seconds > 0
        return 2

    async def fake_fetch_rows(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> list[dict[str, object]]:
        captured_queries.append(query)
        assert timeout_seconds > 0
        return [
            {
                "symbol": "990001",
                "trade_date": date(2024, 1, 2),
                "adjust": "qfq",
                "close": 10.0,
                "high": 10.5,
                "low": 9.9,
                "amount": 1000.0,
                "volume": 100.0,
            }
        ]

    monkeypatch.setattr(query_kline_module.db, "fetch_value", fake_fetch_value)
    monkeypatch.setattr(query_kline_module.db, "fetch_rows", fake_fetch_rows)

    result_none = asyncio.run(
        query_kline_bulk_handler(QueryKlineBulkParams(symbols=None))
    )
    result_empty = asyncio.run(
        query_kline_bulk_handler(QueryKlineBulkParams(symbols=[]))
    )

    assert result_none.success is True
    assert result_empty.success is True
    assert len(captured_queries) == 2
    assert "ANY(" not in captured_queries[0]
    assert "ANY(" not in captured_queries[1]


def test_query_kline_bulk_fields_empty_uses_default_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_value(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> object:
        return 1

    async def fake_fetch_rows(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> list[dict[str, object]]:
        return [
            {
                "symbol": "600519",
                "trade_date": date(2024, 1, 2),
                "adjust": "qfq",
                "close": 10.0,
                "high": 10.5,
                "low": 9.8,
                "amount": 1000.0,
                "volume": 200.0,
            }
        ]

    monkeypatch.setattr(query_kline_module.db, "fetch_value", fake_fetch_value)
    monkeypatch.setattr(query_kline_module.db, "fetch_rows", fake_fetch_rows)

    result = asyncio.run(
        query_kline_bulk_handler(QueryKlineBulkParams(symbols=["600519"], fields=[]))
    )

    assert result.success is True
    grouped = result.result.get("grouped")
    assert isinstance(grouped, dict)
    assert "600519" in grouped
    assert "close" in grouped["600519"][0]


def test_query_kline_bulk_adjust_filter_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_params: list[tuple[object, ...]] = []

    async def fake_fetch_value(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> object:
        captured_params.append(params)
        return 1

    async def fake_fetch_rows(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> list[dict[str, object]]:
        captured_params.append(params)
        return [
            {
                "symbol": "600519",
                "trade_date": date(2024, 1, 3),
                "adjust": "hfq",
                "close": 10.1,
                "high": 10.2,
                "low": 9.7,
                "amount": 1100.0,
                "volume": 210.0,
            }
        ]

    monkeypatch.setattr(query_kline_module.db, "fetch_value", fake_fetch_value)
    monkeypatch.setattr(query_kline_module.db, "fetch_rows", fake_fetch_rows)

    result = asyncio.run(
        query_kline_bulk_handler(QueryKlineBulkParams(symbols=["600519"], adjust="hfq"))
    )

    assert result.success is True
    assert captured_params[0][0] == "hfq"
    assert captured_params[1][0] == "hfq"
    grouped = result.result.get("grouped")
    assert isinstance(grouped, dict)
    for rows in grouped.values():
        for row in rows:
            assert row.get("adjust") == "hfq"


def test_query_kline_bulk_truncate_60_per_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_date = date(2024, 1, 1)

    async def fake_fetch_value(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> object:
        return 140

    async def fake_fetch_rows(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for idx in range(70):
            rows.append(
                {
                    "symbol": "990001",
                    "trade_date": base_date + timedelta(days=200 - idx),
                    "adjust": "qfq",
                    "close": 10.0 + idx,
                    "high": 10.5 + idx,
                    "low": 9.5 + idx,
                    "amount": 1000.0 + idx,
                    "volume": 200.0 + idx,
                }
            )
            rows.append(
                {
                    "symbol": "990002",
                    "trade_date": base_date + timedelta(days=200 - idx),
                    "adjust": "qfq",
                    "close": 11.0 + idx,
                    "high": 11.5 + idx,
                    "low": 10.5 + idx,
                    "amount": 1100.0 + idx,
                    "volume": 210.0 + idx,
                }
            )
        return rows

    monkeypatch.setattr(query_kline_module.db, "fetch_value", fake_fetch_value)
    monkeypatch.setattr(query_kline_module.db, "fetch_rows", fake_fetch_rows)

    result = asyncio.run(
        query_kline_bulk_handler(
            QueryKlineBulkParams(
                symbols=["990001", "990002"],
                adjust="qfq",
                per_symbol_limit=60,
            )
        )
    )

    assert result.success is True
    grouped = result.result.get("grouped")
    assert isinstance(grouped, dict)
    assert len(grouped["990001"]) <= 60
    assert len(grouped["990002"]) <= 60
    meta = result.result.get("meta")
    assert isinstance(meta, dict)
    assert meta.get("truncated") is True


def test_query_kline_bulk_too_many_symbols_raises() -> None:
    symbols = [f"{900000 + idx:06d}" for idx in range(501)]
    params = QueryKlineBulkParams(symbols=symbols)

    with pytest.raises(ValueError, match="too many symbols"):
        asyncio.run(query_kline_bulk_handler(params))


def test_query_kline_bulk_row_cap_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KLINE_BULK_MAX_ROWS", "50")
    get_settings.cache_clear()

    async def fake_fetch_value(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> object:
        return 120

    async def fake_fetch_rows(
        query: str,
        params: tuple[object, ...],
        timeout_seconds: float,
    ) -> list[dict[str, object]]:
        assert params[-1] == 50
        return [
            {
                "symbol": "990001",
                "trade_date": date(2024, 1, 2),
                "adjust": "qfq",
                "close": 10.0,
                "high": 10.5,
                "low": 9.8,
                "amount": 1000.0,
                "volume": 200.0,
            }
        ]

    monkeypatch.setattr(query_kline_module.db, "fetch_value", fake_fetch_value)
    monkeypatch.setattr(query_kline_module.db, "fetch_rows", fake_fetch_rows)

    result = asyncio.run(
        query_kline_bulk_handler(QueryKlineBulkParams(symbols=["990001"], adjust="qfq"))
    )

    assert result.success is True
    meta = result.result.get("meta")
    assert isinstance(meta, dict)
    assert meta.get("row_cap_applied") is True

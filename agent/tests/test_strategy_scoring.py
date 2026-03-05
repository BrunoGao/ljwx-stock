# ruff: noqa: E402

import asyncio
from datetime import date, timedelta
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
REPO_ROOT = PROJECT_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import get_settings
from app.models import ToolExecutionResult
from app.strategy.ensemble_v1 import run_ensemble_v1


def _build_rows(symbol: str, start_day: date, days: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx in range(days):
        trade_day = start_day + timedelta(days=idx)
        close = 100.0 + idx * 0.6
        rows.append(
            {
                "symbol": symbol,
                "trade_date": trade_day.isoformat(),
                "adjust": "qfq",
                "close": close,
                "high": close + 1.5,
                "low": close - 1.2,
                "amount": 20000000.0 + idx * 1000,
                "volume": 100000.0 + idx * 200,
            }
        )
    return rows


@pytest.fixture(autouse=True)
def _prepare_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/ljwx-stock"
    )
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("WRITE_RECO", "true")
    monkeypatch.setenv("DISPLAY_TOP_N", "20")
    monkeypatch.setenv("CANDIDATE_POOL_SIZE", "300")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_bulk_called(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"bulk": 0, "single": 0}
    captured_adjust: list[str] = []

    async def fake_bulk_handler(params) -> ToolExecutionResult:
        calls["bulk"] += 1
        captured_adjust.append(params.adjust)
        grouped = {
            "600519": _build_rows("600519", date(2024, 1, 1), 60),
            "000001": _build_rows("000001", date(2024, 1, 1), 60),
        }
        return ToolExecutionResult(
            success=True,
            result={
                "grouped": grouped,
                "meta": {
                    "total_rows_before_truncate": 120,
                    "total_symbols": 2,
                    "truncated": False,
                    "row_cap_applied": False,
                },
            },
        )

    async def fake_single_handler(_params) -> ToolExecutionResult:
        calls["single"] += 1
        return ToolExecutionResult(success=True, result={})

    async def fake_latest_trade_date(adjust: str) -> date:
        assert adjust == "qfq"
        return date(2024, 3, 31)

    async def fake_insert(rows) -> int:
        return len(rows)

    monkeypatch.setattr(
        "app.tools.query_kline.query_kline_bulk_handler", fake_bulk_handler
    )
    monkeypatch.setattr(
        "agent.app.tools.query_kline.query_kline_bulk_handler",
        fake_bulk_handler,
        raising=False,
    )
    monkeypatch.setattr(
        "app.tools.query_kline.query_kline_handler", fake_single_handler
    )
    monkeypatch.setattr(
        "agent.app.tools.query_kline.query_kline_handler",
        fake_single_handler,
        raising=False,
    )
    monkeypatch.setattr(
        "app.strategy.ensemble_v1.db.get_latest_trade_date", fake_latest_trade_date
    )
    monkeypatch.setattr(
        "app.strategy.ensemble_v1.db.insert_reco_daily_rows", fake_insert
    )

    result = asyncio.run(run_ensemble_v1(symbols=None, end_date=None))

    assert calls["bulk"] == 1
    assert calls["single"] == 0
    assert captured_adjust == ["qfq"]
    assert int(result["candidate_count"]) > 0

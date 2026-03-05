# ruff: noqa: E402

import asyncio
from datetime import date, timedelta
from decimal import Decimal
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
from app.strategy.base import StrategySignal
from app.strategy.ensemble_v1 import merge_strategy_signals, run_ensemble_v1


def _build_rows(symbol: str, start_day: date, days: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx in range(days):
        trade_day = start_day + timedelta(days=idx)
        close = 20.0 + idx * 0.5
        rows.append(
            {
                "symbol": symbol,
                "trade_date": trade_day.isoformat(),
                "adjust": "qfq",
                "close": close,
                "high": close + 0.8,
                "low": close - 0.7,
                "amount": 25000000.0,
                "volume": 120000.0,
            }
        )
    return rows


@pytest.fixture(autouse=True)
def _prepare_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/ljwx-stock"
    )
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("DISPLAY_TOP_N", "20")
    monkeypatch.setenv("CANDIDATE_POOL_SIZE", "300")
    monkeypatch.setenv("WRITE_RECO", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_merge_strategy_signals_weights() -> None:
    signals = {
        "momentum_rule_v1": {
            "600519": StrategySignal(
                symbol="600519",
                trade_date=date(2024, 3, 1),
                strategy_name="momentum_rule_v1",
                score=Decimal("10"),
                confidence=Decimal("0.8"),
                reason_json={},
            )
        },
        "technical_pattern_v1": {
            "600519": StrategySignal(
                symbol="600519",
                trade_date=date(2024, 3, 1),
                strategy_name="technical_pattern_v1",
                score=Decimal("20"),
                confidence=Decimal("0.4"),
                reason_json={},
            )
        },
    }

    merged = merge_strategy_signals(
        signals_by_strategy=signals,
        weights={
            "momentum_rule_v1": Decimal("0.6"),
            "technical_pattern_v1": Decimal("0.4"),
        },
    )

    score, confidence, _reason, _trade_date = merged["600519"]
    assert score == Decimal("14")
    assert confidence == Decimal("0.64")


def test_candidate_vs_display(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_bulk_handler(params) -> ToolExecutionResult:
        assert params.adjust == "qfq"
        grouped = {
            f"{990000 + idx:06d}": _build_rows(
                f"{990000 + idx:06d}", date(2024, 1, 1), 60
            )
            for idx in range(350)
        }
        return ToolExecutionResult(
            success=True,
            result={
                "grouped": grouped,
                "meta": {
                    "total_rows_before_truncate": 350 * 60,
                    "total_symbols": 350,
                    "truncated": False,
                    "row_cap_applied": False,
                },
            },
        )

    async def fake_latest_trade_date(adjust: str) -> date:
        assert adjust == "qfq"
        return date(2024, 3, 31)

    inserted_counts: list[int] = []

    async def fake_insert(rows) -> int:
        inserted_counts.append(len(rows))
        return len(rows)

    monkeypatch.setattr(
        "app.tools.query_kline.query_kline_bulk_handler", fake_bulk_handler
    )
    monkeypatch.setattr(
        "app.strategy.ensemble_v1.db.get_latest_trade_date", fake_latest_trade_date
    )
    monkeypatch.setattr(
        "app.strategy.ensemble_v1.db.insert_reco_daily_rows", fake_insert
    )

    result = asyncio.run(run_ensemble_v1(symbols=None, end_date=None))

    assert int(result["candidate_count"]) == 300
    assert int(result["display_count"]) == 20
    display_rows = result.get("display_rows")
    assert isinstance(display_rows, list)
    assert len(display_rows) == 20
    assert inserted_counts == [300]

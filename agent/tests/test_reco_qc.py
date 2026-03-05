# ruff: noqa: E402

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.qc.reco_qc import (
    evaluate_overlap_check,
    evaluate_row_count_check,
    evaluate_score_distribution_check,
)


def test_qc_cold_start_row_count_pass() -> None:
    result = evaluate_row_count_check(
        trade_date=date(2026, 3, 4),
        strategy_name="qlib_lightgbm_v1",
        row_count=100,
        history_counts=[98, 102, 101],
        cold_start_min=5,
    )

    assert result.status == "pass"
    assert result.detail_json.get("note") == "cold_start"


def test_qc_zero_rows_is_error() -> None:
    result = evaluate_row_count_check(
        trade_date=date(2026, 3, 4),
        strategy_name="qlib_lightgbm_v1",
        row_count=0,
        history_counts=[90, 92, 94, 96, 98],
        cold_start_min=5,
    )

    assert result.status == "error"


def test_qc_overlap_full_is_error() -> None:
    symbols = [f"{600000 + idx}" for idx in range(20)]
    result = evaluate_overlap_check(
        trade_date=date(2026, 3, 4),
        strategy_name="qlib_lightgbm_v1",
        today_symbols=symbols,
        yesterday_symbols=symbols,
        warn_threshold=Decimal("0.9"),
        error_threshold=Decimal("1.0"),
    )

    assert result.status == "error"


def test_qc_overlap_warn() -> None:
    today = [f"{600000 + idx}" for idx in range(20)]
    yesterday = today[:19] + ["700000"]
    result = evaluate_overlap_check(
        trade_date=date(2026, 3, 4),
        strategy_name="qlib_lightgbm_v1",
        today_symbols=today,
        yesterday_symbols=yesterday,
        warn_threshold=Decimal("0.9"),
        error_threshold=Decimal("1.0"),
    )

    assert result.status == "warn"


def test_qc_dynamic_threshold_for_score_distribution() -> None:
    history = [
        Decimal("1.00"),
        Decimal("1.01"),
        Decimal("0.99"),
        Decimal("1.00"),
        Decimal("1.02"),
        Decimal("0.98"),
        Decimal("1.00"),
        Decimal("1.01"),
        Decimal("0.99"),
        Decimal("1.00"),
        Decimal("1.02"),
        Decimal("0.98"),
        Decimal("1.00"),
        Decimal("1.01"),
        Decimal("0.99"),
        Decimal("1.00"),
        Decimal("1.02"),
        Decimal("0.98"),
        Decimal("1.00"),
        Decimal("1.01"),
    ]

    pass_result = evaluate_score_distribution_check(
        trade_date=date(2026, 3, 4),
        strategy_name="qlib_lightgbm_v1",
        today_score_mean=Decimal("1.03"),
        history_score_means=history,
        cold_start_min=5,
    )
    warn_result = evaluate_score_distribution_check(
        trade_date=date(2026, 3, 4),
        strategy_name="qlib_lightgbm_v1",
        today_score_mean=Decimal("1.20"),
        history_score_means=history,
        cold_start_min=5,
    )

    assert pass_result.status == "pass"
    assert warn_result.status == "warn"

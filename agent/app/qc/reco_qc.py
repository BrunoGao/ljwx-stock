from __future__ import annotations

from datetime import date
from decimal import Decimal
from math import sqrt

from pydantic import BaseModel, ConfigDict, Field


class QcCheckResult(BaseModel):
    trade_date: date
    strategy_name: str
    check_name: str
    status: str
    detail_json: dict[str, object] = Field(default_factory=dict)
    threshold_json: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


def _mean_std(values: list[Decimal]) -> tuple[Decimal, Decimal]:
    if len(values) == 0:
        return Decimal("0"), Decimal("0")

    mean = sum(values) / Decimal(len(values))
    variance = sum((value - mean) * (value - mean) for value in values) / Decimal(
        len(values)
    )
    variance_float = float(max(variance, Decimal("0")))
    std = Decimal(str(sqrt(variance_float)))
    return mean, std


def evaluate_row_count_check(
    trade_date: date,
    strategy_name: str,
    row_count: int,
    history_counts: list[int],
    cold_start_min: int,
) -> QcCheckResult:
    if row_count == 0:
        return QcCheckResult(
            trade_date=trade_date,
            strategy_name=strategy_name,
            check_name="row_count_check",
            status="error",
            detail_json={"row_count": row_count, "reason": "row_count_is_zero"},
            threshold_json={},
        )

    if len(history_counts) < cold_start_min:
        return QcCheckResult(
            trade_date=trade_date,
            strategy_name=strategy_name,
            check_name="row_count_check",
            status="pass",
            detail_json={
                "row_count": row_count,
                "note": "cold_start",
                "history_size": len(history_counts),
            },
            threshold_json={},
        )

    history_decimal = [Decimal(value) for value in history_counts]
    mean, std = _mean_std(history_decimal)
    lower = mean - Decimal("2") * std
    upper = mean + Decimal("2") * std

    status = "pass"
    if Decimal(row_count) < lower or Decimal(row_count) > upper:
        status = "warn"

    return QcCheckResult(
        trade_date=trade_date,
        strategy_name=strategy_name,
        check_name="row_count_check",
        status=status,
        detail_json={"row_count": row_count, "history_size": len(history_counts)},
        threshold_json={
            "mean": float(mean),
            "std": float(std),
            "lower": float(lower),
            "upper": float(upper),
        },
    )


def evaluate_score_distribution_check(
    trade_date: date,
    strategy_name: str,
    today_score_mean: Decimal | None,
    history_score_means: list[Decimal],
    cold_start_min: int,
) -> QcCheckResult:
    if today_score_mean is None:
        return QcCheckResult(
            trade_date=trade_date,
            strategy_name=strategy_name,
            check_name="score_distribution_check",
            status="error",
            detail_json={"reason": "missing_today_score_mean"},
            threshold_json={},
        )

    if len(history_score_means) < cold_start_min:
        return QcCheckResult(
            trade_date=trade_date,
            strategy_name=strategy_name,
            check_name="score_distribution_check",
            status="pass",
            detail_json={
                "today_mean": float(today_score_mean),
                "note": "cold_start",
                "history_size": len(history_score_means),
            },
            threshold_json={},
        )

    mean, std = _mean_std(history_score_means)
    deviation = abs(today_score_mean - mean)

    if std == 0:
        status = "warn" if deviation > 0 else "pass"
        z_score = Decimal("999") if deviation > 0 else Decimal("0")
    else:
        z_score = deviation / std
        status = "warn" if z_score > Decimal("3") else "pass"

    return QcCheckResult(
        trade_date=trade_date,
        strategy_name=strategy_name,
        check_name="score_distribution_check",
        status=status,
        detail_json={
            "today_mean": float(today_score_mean),
            "deviation": float(deviation),
            "history_size": len(history_score_means),
        },
        threshold_json={
            "mean": float(mean),
            "std": float(std),
            "z_score": float(z_score),
        },
    )


def evaluate_overlap_check(
    trade_date: date,
    strategy_name: str,
    today_symbols: list[str],
    yesterday_symbols: list[str],
    warn_threshold: Decimal,
    error_threshold: Decimal,
) -> QcCheckResult:
    today_set = set(today_symbols)
    yesterday_set = set(yesterday_symbols)

    denominator = max(len(today_set), len(yesterday_set), 1)
    intersection_size = len(today_set.intersection(yesterday_set))
    overlap = Decimal(intersection_size) / Decimal(denominator)

    status = "pass"
    if overlap >= error_threshold:
        status = "error"
    elif overlap >= warn_threshold:
        status = "warn"

    return QcCheckResult(
        trade_date=trade_date,
        strategy_name=strategy_name,
        check_name="overlap_check",
        status=status,
        detail_json={
            "intersection_size": intersection_size,
            "today_size": len(today_set),
            "yesterday_size": len(yesterday_set),
            "denominator": denominator,
            "overlap": float(overlap),
        },
        threshold_json={
            "warn_threshold": float(warn_threshold),
            "error_threshold": float(error_threshold),
        },
    )

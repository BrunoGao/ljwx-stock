from __future__ import annotations

from datetime import date
from decimal import Decimal
import logging

from app import db
from app.config import get_settings
from app.metrics import set_reco_qc_status
from app.qc.reco_qc import (
    QcCheckResult,
    evaluate_overlap_check,
    evaluate_row_count_check,
    evaluate_score_distribution_check,
)

logger = logging.getLogger(__name__)


def _to_decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _result_to_payload(result: QcCheckResult) -> dict[str, object]:
    return {
        "trade_date": result.trade_date.isoformat(),
        "strategy_name": result.strategy_name,
        "check_name": result.check_name,
        "status": result.status,
        "detail_json": result.detail_json,
        "threshold_json": result.threshold_json,
    }


async def _resolve_latest_trade_date(
    strategy_name: str, timeout_seconds: float
) -> date:
    latest_value = await db.fetch_value(
        query="""
        SELECT max(trade_date)
        FROM market.reco_daily
        WHERE strategy_name = $1
        """,
        params=(strategy_name,),
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(latest_value, date):
        raise ValueError(f"未找到策略 {strategy_name} 的推荐数据")
    return latest_value


async def _fetch_history_row_counts(
    strategy_name: str,
    trade_date: date,
    lookback_days: int,
    timeout_seconds: float,
) -> list[int]:
    rows = await db.fetch_rows(
        query="""
        SELECT trade_date, count(*)::bigint AS row_count
        FROM market.reco_daily
        WHERE strategy_name = $1
          AND trade_date < $2
        GROUP BY trade_date
        ORDER BY trade_date DESC
        LIMIT $3
        """,
        params=(strategy_name, trade_date, lookback_days),
        timeout_seconds=timeout_seconds,
    )

    history_counts: list[int] = []
    for row in rows:
        value = row.get("row_count")
        if isinstance(value, int):
            history_counts.append(value)
    return history_counts


async def _fetch_today_row_count(
    strategy_name: str,
    trade_date: date,
    timeout_seconds: float,
) -> int:
    value = await db.fetch_value(
        query="""
        SELECT count(*)::bigint
        FROM market.reco_daily
        WHERE trade_date = $1
          AND strategy_name = $2
        """,
        params=(trade_date, strategy_name),
        timeout_seconds=timeout_seconds,
    )
    if isinstance(value, int):
        return value
    return 0


async def _fetch_today_score_mean(
    strategy_name: str,
    trade_date: date,
    timeout_seconds: float,
) -> Decimal | None:
    value = await db.fetch_value(
        query="""
        SELECT avg(score)::double precision
        FROM market.reco_daily
        WHERE trade_date = $1
          AND strategy_name = $2
        """,
        params=(trade_date, strategy_name),
        timeout_seconds=timeout_seconds,
    )
    return _to_decimal_or_none(value)


async def _fetch_history_score_means(
    strategy_name: str,
    trade_date: date,
    lookback_days: int,
    timeout_seconds: float,
) -> list[Decimal]:
    rows = await db.fetch_rows(
        query="""
        SELECT trade_date, avg(score)::double precision AS mean_score
        FROM market.reco_daily
        WHERE strategy_name = $1
          AND trade_date < $2
        GROUP BY trade_date
        ORDER BY trade_date DESC
        LIMIT $3
        """,
        params=(strategy_name, trade_date, lookback_days),
        timeout_seconds=timeout_seconds,
    )

    means: list[Decimal] = []
    for row in rows:
        decimal_value = _to_decimal_or_none(row.get("mean_score"))
        if decimal_value is not None:
            means.append(decimal_value)
    return means


async def _fetch_top_symbols(
    strategy_name: str,
    trade_date: date,
    top_n: int,
    timeout_seconds: float,
) -> list[str]:
    rows = await db.fetch_rows(
        query="""
        SELECT symbol
        FROM market.reco_daily
        WHERE trade_date = $1
          AND strategy_name = $2
        ORDER BY score DESC NULLS LAST
        LIMIT $3
        """,
        params=(trade_date, strategy_name, top_n),
        timeout_seconds=timeout_seconds,
    )

    symbols: list[str] = []
    for row in rows:
        symbol = row.get("symbol")
        if isinstance(symbol, str):
            symbols.append(symbol)
    return symbols


async def _fetch_previous_trade_date(
    strategy_name: str,
    trade_date: date,
    timeout_seconds: float,
) -> date | None:
    value = await db.fetch_value(
        query="""
        SELECT max(trade_date)
        FROM market.reco_daily
        WHERE strategy_name = $1
          AND trade_date < $2
        """,
        params=(strategy_name, trade_date),
        timeout_seconds=timeout_seconds,
    )
    if isinstance(value, date):
        return value
    return None


async def run_reco_qc(
    trade_date: date | None,
    strategy_name: str,
    top_n: int = 20,
) -> dict[str, object]:
    settings = get_settings()
    timeout_seconds = settings.kline_query_timeout_seconds

    effective_trade_date = trade_date
    if effective_trade_date is None:
        effective_trade_date = await _resolve_latest_trade_date(
            strategy_name=strategy_name,
            timeout_seconds=timeout_seconds,
        )

    today_row_count = await _fetch_today_row_count(
        strategy_name=strategy_name,
        trade_date=effective_trade_date,
        timeout_seconds=timeout_seconds,
    )
    history_counts = await _fetch_history_row_counts(
        strategy_name=strategy_name,
        trade_date=effective_trade_date,
        lookback_days=settings.qc_lookback_days,
        timeout_seconds=timeout_seconds,
    )

    today_score_mean = await _fetch_today_score_mean(
        strategy_name=strategy_name,
        trade_date=effective_trade_date,
        timeout_seconds=timeout_seconds,
    )
    history_score_means = await _fetch_history_score_means(
        strategy_name=strategy_name,
        trade_date=effective_trade_date,
        lookback_days=settings.qc_lookback_days,
        timeout_seconds=timeout_seconds,
    )

    today_symbols = await _fetch_top_symbols(
        strategy_name=strategy_name,
        trade_date=effective_trade_date,
        top_n=top_n,
        timeout_seconds=timeout_seconds,
    )

    yesterday_trade_date = await _fetch_previous_trade_date(
        strategy_name=strategy_name,
        trade_date=effective_trade_date,
        timeout_seconds=timeout_seconds,
    )
    yesterday_symbols: list[str] = []
    if yesterday_trade_date is not None:
        yesterday_symbols = await _fetch_top_symbols(
            strategy_name=strategy_name,
            trade_date=yesterday_trade_date,
            top_n=top_n,
            timeout_seconds=timeout_seconds,
        )

    results = [
        evaluate_row_count_check(
            trade_date=effective_trade_date,
            strategy_name=strategy_name,
            row_count=today_row_count,
            history_counts=history_counts,
            cold_start_min=settings.qc_cold_start_min,
        ),
        evaluate_score_distribution_check(
            trade_date=effective_trade_date,
            strategy_name=strategy_name,
            today_score_mean=today_score_mean,
            history_score_means=history_score_means,
            cold_start_min=settings.qc_cold_start_min,
        ),
        evaluate_overlap_check(
            trade_date=effective_trade_date,
            strategy_name=strategy_name,
            today_symbols=today_symbols,
            yesterday_symbols=yesterday_symbols,
            warn_threshold=settings.qc_overlap_warn_threshold,
            error_threshold=settings.qc_overlap_error_threshold,
        ),
    ]

    for result in results:
        await db.insert_reco_qc_log(
            trade_date=result.trade_date,
            strategy_name=result.strategy_name,
            check_name=result.check_name,
            status=result.status,
            detail_json=result.detail_json,
            threshold_json=result.threshold_json,
        )
        set_reco_qc_status(
            strategy_name=result.strategy_name,
            check_name=result.check_name,
            status=result.status,
        )

        if result.status == "error":
            logger.error(
                "QC 检查失败",
                extra={
                    "trade_date": result.trade_date.isoformat(),
                    "strategy_name": result.strategy_name,
                    "check_name": result.check_name,
                    "detail": result.detail_json,
                },
            )
        elif result.status == "warn":
            logger.warning(
                "QC 检查告警",
                extra={
                    "trade_date": result.trade_date.isoformat(),
                    "strategy_name": result.strategy_name,
                    "check_name": result.check_name,
                    "detail": result.detail_json,
                },
            )

    return {
        "trade_date": effective_trade_date.isoformat(),
        "strategy_name": strategy_name,
        "checks": [_result_to_payload(result) for result in results],
    }

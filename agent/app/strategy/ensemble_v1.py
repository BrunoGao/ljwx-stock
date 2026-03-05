from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app import db
from app.config import get_settings
from app.strategy.base import StrategyFeature, StrategyReco, StrategySignal
from app.strategy.registry import list_strategies, register_builtin_strategies
from app.tools import query_kline as query_kline_module
from app.tools.query_kline import QueryKlineBulkParams


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def compute_params_hash(params: dict[str, object]) -> str:
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest[:16]


def _calculate_volatility_20d(closes: list[Decimal]) -> Decimal:
    if len(closes) < 21:
        return Decimal("0")

    returns: list[Decimal] = []
    window = closes[-21:]
    for idx in range(1, len(window)):
        prev_close = window[idx - 1]
        curr_close = window[idx]
        if prev_close == 0:
            continue
        returns.append(curr_close / prev_close - Decimal("1"))

    if len(returns) == 0:
        return Decimal("0")

    mean = sum(returns) / Decimal(len(returns))
    variance = sum((ret - mean) * (ret - mean) for ret in returns) / Decimal(
        len(returns)
    )
    if variance < 0:
        return Decimal("0")
    return variance.sqrt()


def _extract_features(
    grouped_rows: dict[str, list[dict[str, object]]],
    min_amount_avg: Decimal,
) -> tuple[list[StrategyFeature], int, int]:
    features: list[StrategyFeature] = []
    filtered_count = 0
    insufficient_count = 0

    for symbol, rows in grouped_rows.items():
        if len(rows) < 60:
            insufficient_count += 1
            continue

        closes = [_to_decimal(row.get("close")) for row in rows]
        highs = [_to_decimal(row.get("high")) for row in rows[-20:]]
        lows = [_to_decimal(row.get("low")) for row in rows[-20:]]
        amounts = [_to_decimal(row.get("amount")) for row in rows[-20:]]

        latest_close = closes[-1]
        close_5d_ago = closes[-6]
        if close_5d_ago == 0:
            insufficient_count += 1
            continue

        ret_5d = latest_close / close_5d_ago - Decimal("1")
        vol_20d = _calculate_volatility_20d(closes)
        amount_avg_20d = (
            sum(amounts) / Decimal(len(amounts)) if amounts else Decimal("0")
        )

        if amount_avg_20d < min_amount_avg:
            filtered_count += 1
            continue

        high_20d = max(highs) if highs else latest_close
        low_20d = min(lows) if lows else latest_close
        if high_20d <= low_20d:
            breakout_20d = Decimal("0.5")
        else:
            breakout_20d = (latest_close - low_20d) / (high_20d - low_20d)

        trade_date_raw = rows[-1].get("trade_date")
        if isinstance(trade_date_raw, str):
            trade_date = date.fromisoformat(trade_date_raw)
        elif isinstance(trade_date_raw, date):
            trade_date = trade_date_raw
        else:
            insufficient_count += 1
            continue

        features.append(
            StrategyFeature(
                symbol=symbol,
                trade_date=trade_date,
                ret_5d=ret_5d,
                vol_20d=vol_20d,
                amount_avg_20d=amount_avg_20d,
                breakout_20d=breakout_20d,
            )
        )

    return features, filtered_count, insufficient_count


def merge_strategy_signals(
    signals_by_strategy: dict[str, dict[str, StrategySignal]],
    weights: dict[str, Decimal],
) -> dict[str, tuple[Decimal, Decimal, dict[str, object], date]]:
    merged: dict[str, tuple[Decimal, Decimal, dict[str, object], date]] = {}
    all_symbols: set[str] = set()
    for strategy_signals in signals_by_strategy.values():
        all_symbols.update(strategy_signals.keys())

    for symbol in all_symbols:
        score_weighted = Decimal("0")
        confidence_weighted = Decimal("0")
        total_weight = Decimal("0")
        reasons: dict[str, object] = {}
        latest_trade_date: date | None = None

        for strategy_name, symbol_signals in signals_by_strategy.items():
            signal = symbol_signals.get(symbol)
            if signal is None:
                continue
            weight = weights.get(strategy_name, Decimal("0"))
            if weight <= 0:
                continue

            score_weighted += signal.score * weight
            confidence_weighted += signal.confidence * weight
            total_weight += weight
            reasons[strategy_name] = {
                "score": float(signal.score),
                "confidence": float(signal.confidence),
                "reason": signal.reason_json,
            }
            latest_trade_date = signal.trade_date

        if total_weight <= 0 or latest_trade_date is None:
            continue

        merged[symbol] = (
            score_weighted / total_weight,
            confidence_weighted / total_weight,
            reasons,
            latest_trade_date,
        )

    return merged


async def run_ensemble_v1(
    symbols: list[str] | None, end_date: date | None
) -> dict[str, object]:
    settings = get_settings()
    adjust = "qfq"

    effective_end_date = end_date
    if effective_end_date is None:
        effective_end_date = await db.get_latest_trade_date(adjust=adjust)

    start_date = effective_end_date - timedelta(days=settings.lookback_days_calendar)

    bulk_result = await query_kline_module.query_kline_bulk_handler(
        QueryKlineBulkParams(
            symbols=symbols,
            start_date=start_date,
            end_date=effective_end_date,
            adjust="qfq",
            fields=["close", "high", "low", "amount", "volume"],
            per_symbol_limit=60,
        )
    )
    if not bulk_result.success:
        raise ValueError(bulk_result.error or "批量行情查询失败")

    grouped = bulk_result.result.get("grouped")
    meta = bulk_result.result.get("meta")
    if not isinstance(grouped, dict) or not isinstance(meta, dict):
        raise ValueError("批量行情结果结构无效")

    min_amount_avg = settings.min_amount_avg
    features, filtered_count, insufficient_count = _extract_features(
        grouped, min_amount_avg
    )

    register_builtin_strategies()
    strategies = list_strategies()

    signals_by_strategy: dict[str, dict[str, StrategySignal]] = {}
    for strategy in strategies:
        strategy_signals = strategy.score(features)
        signals_by_strategy[strategy.name] = {
            signal.symbol: signal for signal in strategy_signals
        }

    weights = {
        "momentum_rule_v1": Decimal("0.6"),
        "technical_pattern_v1": Decimal("0.4"),
    }
    merged = merge_strategy_signals(
        signals_by_strategy=signals_by_strategy, weights=weights
    )

    ordered = sorted(merged.items(), key=lambda item: item[1][0], reverse=True)

    params_for_hash = {
        "symbols": symbols if symbols is not None else [],
        "start_date": start_date.isoformat(),
        "end_date": effective_end_date.isoformat(),
        "adjust": "qfq",
        "lookback_days_calendar": settings.lookback_days_calendar,
        "min_amount_avg": str(min_amount_avg),
        "candidate_pool_size": settings.candidate_pool_size,
    }
    params_hash = compute_params_hash(params_for_hash)

    candidate_limit = settings.candidate_pool_size
    display_limit = min(settings.display_top_n, 50)

    candidate_rows: list[StrategyReco] = []
    for index, (symbol, (score, confidence, reasons, trade_date)) in enumerate(
        ordered[:candidate_limit], start=1
    ):
        reason_json = {
            "filtered": False,
            "threshold": str(min_amount_avg),
            "ensemble": reasons,
        }
        candidate_rows.append(
            StrategyReco(
                symbol=symbol,
                trade_date=trade_date,
                strategy_name="strategy_ensemble_v1",
                score=score,
                confidence=confidence,
                rank=index,
                reason_json=reason_json,
                model_version="strategy_ensemble_v1@v1",
                data_cutoff=effective_end_date,
                code_version=settings.code_version,
                params_hash=params_hash,
            )
        )

    display_rows = candidate_rows[:display_limit]

    written_count = 0
    if settings.write_reco and candidate_rows:
        written_count = await db.insert_reco_daily_rows(candidate_rows)

    return {
        "summary": (
            f"策略完成：候选池 {len(candidate_rows)} 条，展示 {len(display_rows)} 条，"
            f"数据截面 {effective_end_date.isoformat()}。"
        ),
        "strategy_name": "strategy_ensemble_v1",
        "candidate_count": len(candidate_rows),
        "display_count": len(display_rows),
        "display_rows": [
            {
                "rank": row.rank,
                "symbol": row.symbol,
                "score": float(row.score),
                "confidence": float(row.confidence),
            }
            for row in display_rows
        ],
        "data_cutoff": effective_end_date.isoformat(),
        "params_hash": params_hash,
        "written_count": written_count,
        "meta": {
            "total_rows_before_truncate": meta.get("total_rows_before_truncate", 0),
            "total_symbols": meta.get("total_symbols", 0),
            "truncated": meta.get("truncated", False),
            "row_cap_applied": meta.get("row_cap_applied", False),
            "filtered_count": filtered_count,
            "insufficient_count": insufficient_count,
        },
    }

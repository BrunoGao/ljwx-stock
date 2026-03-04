from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import akshare as ak
import pandas as pd
from psycopg2.extensions import connection as PgConnection
import requests

from stock_etl.app.config import Settings
from stock_etl.app.db import KlineRecord, upsert_kline_batch


LOGGER = logging.getLogger("stock_etl")
SYMBOL_PATTERN = re.compile(r"^\d{6}$")


@dataclass(frozen=True)
class DateWindow:
    start: date
    end: date


def previous_quarter_window(today: date) -> DateWindow:
    quarter = (today.month - 1) // 3 + 1
    if quarter == 1:
        year = today.year - 1
        quarter = 4
    else:
        year = today.year
        quarter = quarter - 1

    start_month = (quarter - 1) * 3 + 1
    start = date(year, start_month, 1)

    if start_month == 10:
        end = date(year, 12, 31)
    else:
        next_quarter = date(year, start_month + 3, 1)
        end = next_quarter - timedelta(days=1)
    return DateWindow(start=start, end=end)


def to_date_str(value: date) -> str:
    return value.strftime("%Y%m%d")


def _detect_column(frame: pd.DataFrame, candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    raise ValueError(f"缺少列: {candidates}")


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    return Decimal(text)


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    return int(Decimal(text))


def _call_with_retry(
    fn_name: str,
    fn: Callable[[], pd.DataFrame],
    request_retries: int,
) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(request_retries + 1):
        try:
            return fn()
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt < request_retries:
                sleep_seconds = 1.0 * (attempt + 1)
                LOGGER.warning(
                    "上游接口调用失败，准备重试",
                    extra={
                        "function": fn_name,
                        "attempt": attempt + 1,
                        "max_attempts": request_retries + 1,
                        "sleep_seconds": sleep_seconds,
                        "error": str(exc),
                    },
                )
                time.sleep(sleep_seconds)
                continue
            break
    raise RuntimeError(f"{fn_name} 调用失败: {last_error}")


def load_symbol_universe(symbol_limit: int, request_retries: int) -> list[str]:
    frame = _call_with_retry(
        fn_name="stock_zh_a_spot_em",
        fn=ak.stock_zh_a_spot_em,
        request_retries=request_retries,
    )
    code_col = _detect_column(frame, ["代码", "symbol", "代码 "])
    symbols = [
        str(code).strip()
        for code in frame[code_col].tolist()
        if SYMBOL_PATTERN.match(str(code).strip())
    ]
    symbols = sorted(set(symbols))
    if symbol_limit > 0:
        return symbols[:symbol_limit]
    return symbols


def load_trade_dates_from_index(request_retries: int) -> list[date]:
    frame = _call_with_retry(
        fn_name="stock_zh_index_daily_em",
        fn=lambda: ak.stock_zh_index_daily_em(symbol="sh000001"),
        request_retries=request_retries,
    )
    date_col = _detect_column(frame, ["date", "日期"])
    dates = pd.to_datetime(frame[date_col], errors="coerce").dt.date.dropna().tolist()
    unique_dates = sorted(set(dates))
    if not unique_dates:
        raise RuntimeError("无法获取交易日历")
    return unique_dates


def decide_window(settings: Settings, today: date) -> DateWindow:
    if settings.run_mode == "backfill":
        trade_dates = load_trade_dates_from_index(settings.request_retries)
        eligible = [d for d in trade_dates if d <= today]
        if not eligible:
            raise RuntimeError("交易日历为空，无法计算回灌区间")
        if len(eligible) <= settings.trading_days:
            start = eligible[0]
        else:
            start = eligible[-settings.trading_days]
        end = eligible[-1]
        return DateWindow(start=start, end=end)

    if settings.run_mode == "daily":
        start = today - timedelta(days=settings.daily_lookback_calendar_days)
        return DateWindow(start=start, end=today)

    if settings.run_mode == "reconcile":
        quarter_window = previous_quarter_window(today)
        max_lookback_start = today - timedelta(
            days=settings.reconcile_lookback_calendar_days
        )
        start = min(quarter_window.start, max_lookback_start)
        return DateWindow(start=start, end=quarter_window.end)

    raise ValueError(f"未知 RUN_MODE: {settings.run_mode}")


def fetch_symbol_kline(
    symbol: str, window: DateWindow, adjust: str, request_retries: int
) -> pd.DataFrame:
    start_str = to_date_str(window.start)
    end_str = to_date_str(window.end)

    last_error: Exception | None = None
    for attempt in range(request_retries + 1):
        try:
            frame = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_str,
                end_date=end_str,
                adjust=adjust,
            )
            return frame
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt < request_retries:
                time.sleep(0.8 * (attempt + 1))
                continue
            break

    raise RuntimeError(f"拉取行情失败 symbol={symbol}: {last_error}")


def convert_frame_to_records(
    symbol: str, adjust: str, frame: pd.DataFrame
) -> list[KlineRecord]:
    if frame.empty:
        return []

    date_col = _detect_column(frame, ["日期", "date"])
    open_col = _detect_column(frame, ["开盘", "open"])
    high_col = _detect_column(frame, ["最高", "high"])
    low_col = _detect_column(frame, ["最低", "low"])
    close_col = _detect_column(frame, ["收盘", "close"])
    vol_col = _detect_column(frame, ["成交量", "volume"])
    amount_col = _detect_column(frame, ["成交额", "amount"])

    turnover_col = "换手率" if "换手率" in frame.columns else None
    amplitude_col = "振幅" if "振幅" in frame.columns else None
    pct_chg_col = "涨跌幅" if "涨跌幅" in frame.columns else None
    chg_col = "涨跌额" if "涨跌额" in frame.columns else None

    records: list[KlineRecord] = []
    for row in frame.to_dict(orient="records"):
        trade_day_raw = row.get(date_col)
        trade_day = pd.to_datetime(trade_day_raw, errors="coerce")
        if pd.isna(trade_day):
            continue

        turnover_value: Decimal | None = (
            _to_decimal(row.get(turnover_col)) if turnover_col else None
        )
        amplitude_value: Decimal | None = (
            _to_decimal(row.get(amplitude_col)) if amplitude_col else None
        )
        pct_chg_value: Decimal | None = (
            _to_decimal(row.get(pct_chg_col)) if pct_chg_col else None
        )
        chg_value: Decimal | None = _to_decimal(row.get(chg_col)) if chg_col else None

        records.append(
            KlineRecord(
                symbol=symbol,
                trade_date=trade_day.date(),
                adjust=adjust,
                open=_to_decimal(row.get(open_col)),
                high=_to_decimal(row.get(high_col)),
                low=_to_decimal(row.get(low_col)),
                close=_to_decimal(row.get(close_col)),
                volume=_to_int(row.get(vol_col)),
                amount=_to_decimal(row.get(amount_col)),
                turnover=turnover_value,
                amplitude=amplitude_value,
                pct_chg=pct_chg_value,
                chg=chg_value,
                source="akshare",
            )
        )

    records.sort(key=lambda item: item.trade_date)
    return records


def run_ingest(conn: PgConnection, settings: Settings) -> dict[str, int | str]:
    today = datetime.now().date()
    window = decide_window(settings, today)
    symbols = load_symbol_universe(settings.symbol_limit, settings.request_retries)

    total_symbols = len(symbols)
    success_symbols = 0
    failed_symbols = 0
    written_rows = 0

    LOGGER.info(
        "开始执行行情入库",
        extra={
            "run_mode": settings.run_mode,
            "adjust": settings.adjust,
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "symbols": total_symbols,
        },
    )

    for index, symbol in enumerate(symbols, start=1):
        try:
            frame = fetch_symbol_kline(
                symbol, window, settings.adjust, settings.request_retries
            )
            records = convert_frame_to_records(symbol, settings.adjust, frame)

            if records:
                for offset in range(0, len(records), settings.batch_size):
                    batch = records[offset : offset + settings.batch_size]
                    written_rows += upsert_kline_batch(conn, batch)

            success_symbols += 1
            if index % 100 == 0:
                LOGGER.info(
                    "入库进度",
                    extra={
                        "processed": index,
                        "total": total_symbols,
                        "written_rows": written_rows,
                        "failed_symbols": failed_symbols,
                    },
                )
        except (RuntimeError, ValueError, TypeError) as exc:
            failed_symbols += 1
            LOGGER.warning(
                "单个标的处理失败",
                extra={
                    "symbol": symbol,
                    "error": str(exc),
                    "processed": index,
                    "total": total_symbols,
                },
            )
        finally:
            if settings.request_sleep_ms > 0:
                time.sleep(settings.request_sleep_ms / 1000.0)

    LOGGER.info(
        "行情入库结束",
        extra={
            "run_mode": settings.run_mode,
            "adjust": settings.adjust,
            "written_rows": written_rows,
            "success_symbols": success_symbols,
            "failed_symbols": failed_symbols,
        },
    )

    return {
        "run_mode": settings.run_mode,
        "adjust": settings.adjust,
        "written_rows": written_rows,
        "success_symbols": success_symbols,
        "failed_symbols": failed_symbols,
        "window_start": window.start.isoformat(),
        "window_end": window.end.isoformat(),
    }

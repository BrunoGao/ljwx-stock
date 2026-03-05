# ruff: noqa: E402

import asyncio
from datetime import date, timedelta
import os
from pathlib import Path
import sys

import asyncpg
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import db
from app.config import get_settings
from app.tools.query_kline import QueryKlineBulkParams, query_kline_bulk_handler


async def _prepare_table(dsn: str) -> None:
    conn = await asyncpg.connect(dsn=dsn, timeout=5.0)
    try:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS market", timeout=5.0)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market.kline_daily (
                symbol text NOT NULL,
                trade_date date NOT NULL,
                adjust text NOT NULL,
                open double precision,
                high double precision,
                low double precision,
                close double precision,
                volume double precision,
                amount double precision,
                turnover double precision,
                pct_chg double precision,
                amplitude double precision,
                chg double precision
            )
            """,
            timeout=5.0,
        )

        await conn.execute(
            "DELETE FROM market.kline_daily WHERE symbol IN ('990001', '990002')",
            timeout=5.0,
        )

        base_date = date(2024, 1, 1)
        sample_rows: list[tuple[object, ...]] = []
        for index in range(70):
            current_date = base_date + timedelta(days=index)
            sample_rows.append(
                (
                    "990001",
                    current_date,
                    "qfq",
                    10.0 + index,
                    10.5 + index,
                    9.5 + index,
                    10.2 + index,
                    1000.0 + index,
                    2000.0 + index,
                    1.2,
                    0.5,
                    1.0,
                    0.2,
                )
            )
            sample_rows.append(
                (
                    "990002",
                    current_date,
                    "qfq",
                    20.0 + index,
                    20.5 + index,
                    19.5 + index,
                    20.2 + index,
                    2000.0 + index,
                    4000.0 + index,
                    1.5,
                    0.7,
                    1.2,
                    0.4,
                )
            )

        for index in range(10):
            current_date = base_date + timedelta(days=index)
            sample_rows.append(
                (
                    "990001",
                    current_date,
                    "hfq",
                    30.0 + index,
                    30.5 + index,
                    29.5 + index,
                    30.2 + index,
                    3000.0 + index,
                    6000.0 + index,
                    2.0,
                    1.5,
                    2.2,
                    0.9,
                )
            )

        await conn.executemany(
            """
            INSERT INTO market.kline_daily (
                symbol,
                trade_date,
                adjust,
                open,
                high,
                low,
                close,
                volume,
                amount,
                turnover,
                pct_chg,
                amplitude,
                chg
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            sample_rows,
            timeout=5.0,
        )
    finally:
        await conn.close(timeout=5.0)


async def _cleanup_rows(dsn: str) -> None:
    conn = await asyncpg.connect(dsn=dsn, timeout=5.0)
    try:
        await conn.execute(
            "DELETE FROM market.kline_daily WHERE symbol IN ('990001', '990002')",
            timeout=5.0,
        )
    finally:
        await conn.close(timeout=5.0)


async def _run_integration(dsn: str) -> None:
    os.environ["DATABASE_URL"] = dsn
    os.environ.setdefault("API_KEY", "integration-api-key")
    get_settings.cache_clear()

    await _prepare_table(dsn)

    settings = get_settings()
    await db.init_db_pool(settings)
    try:
        result = await query_kline_bulk_handler(
            QueryKlineBulkParams(
                symbols=["990001", "990002"],
                adjust="qfq",
                per_symbol_limit=60,
                fields=["close", "high", "low", "amount", "volume"],
            )
        )

        assert result.success is True
        grouped = result.result.get("grouped")
        assert isinstance(grouped, dict)
        assert set(grouped.keys()) == {"990001", "990002"}

        for symbol_rows in grouped.values():
            assert len(symbol_rows) <= 60
            for row in symbol_rows:
                assert row.get("adjust") == "qfq"
                assert "close" in row

        meta = result.result.get("meta")
        assert isinstance(meta, dict)
        assert "total_rows_before_truncate" in meta
        assert "total_symbols" in meta
        assert "truncated" in meta
        assert "row_cap_applied" in meta
    finally:
        await db.close_db_pool()
        await _cleanup_rows(dsn)
        get_settings.cache_clear()


def test_kline_sql_integration() -> None:
    dsn = os.getenv("DATABASE_URL")
    if dsn is None or dsn.strip() == "":
        pytest.skip("DATABASE_URL not set, skip kline SQL integration test")

    asyncio.run(_run_integration(dsn))

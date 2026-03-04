from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import psycopg2
from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import execute_values


@dataclass(frozen=True)
class KlineRecord:
    symbol: str
    trade_date: date
    adjust: str
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: int | None
    amount: Decimal | None
    turnover: Decimal | None
    amplitude: Decimal | None
    pct_chg: Decimal | None
    chg: Decimal | None
    source: str


def connect_pg(dsn: str) -> PgConnection:
    return psycopg2.connect(dsn=dsn, connect_timeout=10)


def ensure_market_tables(conn: PgConnection) -> None:
    ddl = """
    CREATE SCHEMA IF NOT EXISTS market;

    CREATE TABLE IF NOT EXISTS market.kline_daily (
      symbol text NOT NULL,
      trade_date date NOT NULL,
      adjust text NOT NULL,
      open double precision,
      high double precision,
      low double precision,
      close double precision,
      volume bigint,
      amount numeric(20,2),
      turnover double precision,
      amplitude double precision,
      pct_chg double precision,
      chg double precision,
      source text NOT NULL DEFAULT 'akshare',
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(symbol, trade_date, adjust),
      CONSTRAINT ck_adjust CHECK (adjust IN ('none','qfq','hfq'))
    );

    CREATE INDEX IF NOT EXISTS ix_kline_trade_date
      ON market.kline_daily(trade_date);

    CREATE INDEX IF NOT EXISTS ix_kline_symbol_adj_date
      ON market.kline_daily(symbol, adjust, trade_date);
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def upsert_kline_batch(conn: PgConnection, rows: list[KlineRecord]) -> int:
    if not rows:
        return 0

    sql = """
    INSERT INTO market.kline_daily (
      symbol, trade_date, adjust, open, high, low, close,
      volume, amount, turnover, amplitude, pct_chg, chg, source
    ) VALUES %s
    ON CONFLICT (symbol, trade_date, adjust)
    DO UPDATE SET
      open = EXCLUDED.open,
      high = EXCLUDED.high,
      low = EXCLUDED.low,
      close = EXCLUDED.close,
      volume = EXCLUDED.volume,
      amount = EXCLUDED.amount,
      turnover = EXCLUDED.turnover,
      amplitude = EXCLUDED.amplitude,
      pct_chg = EXCLUDED.pct_chg,
      chg = EXCLUDED.chg,
      source = EXCLUDED.source,
      updated_at = now();
    """

    values = [
        (
            row.symbol,
            row.trade_date,
            row.adjust,
            row.open,
            row.high,
            row.low,
            row.close,
            row.volume,
            row.amount,
            row.turnover,
            row.amplitude,
            row.pct_chg,
            row.chg,
            row.source,
        )
        for row in rows
    ]

    with conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=1000)
    conn.commit()
    return len(values)


def count_qfq_rows(conn: PgConnection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM market.kline_daily WHERE adjust='qfq'")
        row = cur.fetchone()
    if row is None:
        return 0
    return int(row[0])

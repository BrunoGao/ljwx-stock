from datetime import date

import psycopg2


def _format_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def preflight_or_raise(pg_dsn: str) -> dict[str, object]:
    with psycopg2.connect(dsn=pg_dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass('market.kline_daily')")
            regclass_row = cursor.fetchone()
            regclass_value = None if regclass_row is None else regclass_row[0]
            if regclass_value is None:
                raise RuntimeError(
                    "预检失败: market.kline_daily not found; run ETL migration / ingest first"
                )

            cursor.execute(
                """
                SELECT
                    COUNT(*)::bigint AS row_count,
                    COUNT(DISTINCT symbol)::bigint AS symbol_count,
                    MIN(trade_date) AS min_trade_date,
                    MAX(trade_date) AS max_trade_date
                FROM market.kline_daily
                WHERE adjust = %s
                """,
                ("qfq",),
            )
            stats_row = cursor.fetchone()

    if stats_row is None:
        raise RuntimeError("预检失败: 无法读取 qfq 数据统计")

    row_count = int(stats_row[0])
    symbol_count = int(stats_row[1])
    min_trade_date = stats_row[2]
    max_trade_date = stats_row[3]

    if row_count <= 0:
        raise RuntimeError("预检失败: no qfq data in market.kline_daily")

    return {
        "table": "market.kline_daily",
        "adjust": "qfq",
        "row_count": row_count,
        "symbol_count": symbol_count,
        "min_trade_date": _format_date(min_trade_date),
        "max_trade_date": _format_date(max_trade_date),
    }

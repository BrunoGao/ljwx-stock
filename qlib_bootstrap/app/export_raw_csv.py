import csv
from datetime import date
from pathlib import Path

import psycopg2


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} 日期格式错误: {value}") from exc


def _to_qlib_symbol(symbol: str) -> str:
    clean = symbol.strip()
    if len(clean) == 6 and clean.isdigit():
        if clean.startswith("6"):
            return f"SH{clean}"
        return f"SZ{clean}"
    return clean.upper()


def export_raw_csv(
    pg_dsn: str, out_dir: str, start_date: str, end_date: str
) -> dict[str, object]:
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date 不能晚于 end_date")

    raw_root = Path(out_dir)
    features_dir = raw_root / "features"
    features_dir.mkdir(parents=True, exist_ok=True)

    sql = """
        SELECT
            trade_date,
            symbol,
            open,
            high,
            low,
            close,
            volume,
            amount
        FROM market.kline_daily
        WHERE adjust = %s
          AND trade_date >= %s
          AND trade_date <= %s
        ORDER BY symbol, trade_date
    """

    row_count = 0
    symbol_count = 0
    current_symbol = ""
    current_handle = None
    current_writer = None

    try:
        with psycopg2.connect(dsn=pg_dsn) as conn:
            with conn.cursor(name="export_qfq_kline_cursor") as cursor:
                cursor.itersize = 5000
                cursor.execute(sql, ("qfq", start, end))

                for row in cursor:
                    trade_date_raw = row[0]
                    symbol_raw = str(row[1])
                    mapped_symbol = _to_qlib_symbol(symbol_raw)

                    if mapped_symbol != current_symbol:
                        if current_handle is not None:
                            current_handle.close()

                        file_path = features_dir / f"{mapped_symbol}.csv"
                        current_handle = file_path.open(
                            "w", encoding="utf-8", newline=""
                        )
                        current_writer = csv.writer(current_handle)
                        current_writer.writerow(
                            ["date", "open", "high", "low", "close", "volume", "amount"]
                        )
                        current_symbol = mapped_symbol
                        symbol_count += 1

                    if current_writer is None:
                        raise RuntimeError("CSV 写入器未初始化")

                    if not isinstance(trade_date_raw, date):
                        raise ValueError(f"trade_date 类型错误: {trade_date_raw}")

                    current_writer.writerow(
                        [
                            trade_date_raw.isoformat(),
                            row[2],
                            row[3],
                            row[4],
                            row[5],
                            row[6],
                            row[7],
                        ]
                    )
                    row_count += 1
    finally:
        if current_handle is not None:
            current_handle.close()

    return {
        "raw_dir": str(raw_root),
        "features_dir": str(features_dir),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "row_count": row_count,
        "symbol_count": symbol_count,
    }

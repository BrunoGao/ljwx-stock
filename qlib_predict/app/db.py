import json
from hashlib import sha256
from typing import Final

import psycopg2
from psycopg2.extras import execute_batch

_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "symbol",
    "trade_date",
    "strategy_name",
    "score",
    "confidence",
    "rank",
    "reason_json",
    "model_version",
    "data_cutoff",
    "code_version",
    "params_hash",
)


def build_params_hash(params: dict[str, object]) -> str:
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_upsert_sql() -> str:
    return """
    INSERT INTO market.reco_daily (
        symbol,
        trade_date,
        strategy_name,
        score,
        confidence,
        rank,
        reason_json,
        model_version,
        data_cutoff,
        code_version,
        params_hash
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s
    )
    ON CONFLICT (symbol, trade_date, strategy_name) DO UPDATE SET
        score = EXCLUDED.score,
        confidence = EXCLUDED.confidence,
        rank = EXCLUDED.rank,
        reason_json = EXCLUDED.reason_json,
        model_version = EXCLUDED.model_version,
        data_cutoff = EXCLUDED.data_cutoff,
        code_version = EXCLUDED.code_version,
        params_hash = EXCLUDED.params_hash
    """.strip()


def _validate_row(row: dict[str, object]) -> None:
    missing_fields = [field for field in _REQUIRED_FIELDS if field not in row]
    if len(missing_fields) > 0:
        raise ValueError(f"reco 写入缺少字段: {', '.join(missing_fields)}")


def _build_values(row: dict[str, object]) -> tuple[object, ...]:
    _validate_row(row)
    reason_json = row["reason_json"]
    if not isinstance(reason_json, dict):
        raise ValueError("reason_json 必须是对象")

    return (
        row["symbol"],
        row["trade_date"],
        row["strategy_name"],
        float(row["score"]),
        float(row["confidence"]),
        int(row["rank"]),
        json.dumps(reason_json, ensure_ascii=False, separators=(",", ":")),
        row["model_version"],
        row["data_cutoff"],
        row["code_version"],
        row["params_hash"],
    )


def upsert_reco_daily(dsn: str, rows: list[dict[str, object]]) -> int:
    if len(rows) == 0:
        return 0

    sql = build_upsert_sql()
    values = [_build_values(row) for row in rows]

    with psycopg2.connect(dsn=dsn) as conn:
        with conn.cursor() as cursor:
            execute_batch(cursor, sql, values, page_size=500)

    return len(rows)

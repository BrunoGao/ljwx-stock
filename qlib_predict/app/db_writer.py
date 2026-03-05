from __future__ import annotations

from .db import build_params_hash, build_upsert_sql, upsert_reco_daily


def write_reco_daily_rows(dsn: str, rows: list[dict[str, object]]) -> int:
    return upsert_reco_daily(dsn=dsn, rows=rows)


__all__ = [
    "build_params_hash",
    "build_upsert_sql",
    "upsert_reco_daily",
    "write_reco_daily_rows",
]

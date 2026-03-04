from qlib_predict.app.db import build_upsert_sql


def test_upsert_sql_contains_conflict_key() -> None:
    sql = build_upsert_sql()
    assert "ON CONFLICT (symbol, trade_date, strategy_name)" in sql


def test_upsert_sql_does_not_update_created_at() -> None:
    sql = build_upsert_sql()
    assert "created_at =" not in sql

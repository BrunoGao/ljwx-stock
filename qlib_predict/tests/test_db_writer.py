from qlib_predict.app.db_writer import build_upsert_sql


def test_db_writer_upsert_sql_contains_conflict_key() -> None:
    sql = build_upsert_sql()
    assert "ON CONFLICT (symbol, trade_date, strategy_name)" in sql

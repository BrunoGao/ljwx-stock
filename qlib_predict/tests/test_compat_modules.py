from qlib_predict.app import db_writer, model_loader


def test_db_writer_exports_expected_symbols() -> None:
    assert callable(db_writer.build_params_hash)
    assert callable(db_writer.build_upsert_sql)
    assert callable(db_writer.upsert_reco_daily)
    assert callable(db_writer.write_reco_daily_rows)


def test_model_loader_exports_expected_symbols() -> None:
    assert isinstance(model_loader.MODEL_FAMILY, str)
    assert callable(model_loader.resolve_model_date)
    assert callable(model_loader.resolve_model_files)
    assert callable(model_loader.resolve_latest_model_date)
    assert callable(model_loader.resolve_model_artifacts)

from qlib_predict.app.config import get_settings


def test_settings_use_p3a_aliases_when_primary_env_absent(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.delenv("QLIB_PROVIDER_URI", raising=False)
    monkeypatch.delenv("QLIB_MODEL_ROOT", raising=False)
    monkeypatch.delenv("PREDICT_DATE", raising=False)
    monkeypatch.setenv("QLIB_DATA_DIR", "/data/qlib/data")
    monkeypatch.setenv("MODEL_DIR", "/data/qlib/models")
    monkeypatch.setenv("PREDICT_TRADE_DATE", "2026-03-05")

    get_settings.cache_clear()
    settings = get_settings()
    try:
        assert settings.resolved_provider_uri == "/data/qlib/data"
        assert settings.resolved_model_root == "/data/qlib/models"
        assert settings.resolved_predict_date == "2026-03-05"
    finally:
        get_settings.cache_clear()


def test_settings_primary_env_has_higher_priority(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("QLIB_PROVIDER_URI", "/pvc/qlib/cn")
    monkeypatch.setenv("QLIB_MODEL_ROOT", "/pvc/models")
    monkeypatch.setenv("PREDICT_DATE", "2026-03-06")
    monkeypatch.setenv("QLIB_DATA_DIR", "/fallback/data")
    monkeypatch.setenv("MODEL_DIR", "/fallback/models")
    monkeypatch.setenv("PREDICT_TRADE_DATE", "2026-03-05")

    get_settings.cache_clear()
    settings = get_settings()
    try:
        assert settings.resolved_provider_uri == "/pvc/qlib/cn"
        assert settings.resolved_model_root == "/pvc/models"
        assert settings.resolved_predict_date == "2026-03-06"
    finally:
        get_settings.cache_clear()

from qlib_bootstrap.app.train_model import build_params_hash


def test_build_params_hash_stable() -> None:
    params_a: dict[str, object] = {
        "provider_uri": "/data/qlib/qlib_data/cn",
        "horizon_days": 5,
        "lookback_years": 8,
        "feature_set": "Alpha158",
    }
    params_b: dict[str, object] = {
        "feature_set": "Alpha158",
        "lookback_years": 8,
        "horizon_days": 5,
        "provider_uri": "/data/qlib/qlib_data/cn",
    }

    hash_a = build_params_hash(params_a)
    hash_b = build_params_hash(params_b)

    assert hash_a == hash_b
    assert len(hash_a) == 16

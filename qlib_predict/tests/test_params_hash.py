from qlib_predict.app.db import build_params_hash


def test_params_hash_stable() -> None:
    params = {
        "provider_uri": "/data/qlib/qlib_data/cn",
        "model_root": "/data/qlib/artifacts/models",
        "model_date": "20240301",
        "predict_date": "2024-03-01",
        "candidate_pool_size": 300,
    }

    hash_one = build_params_hash(params)
    hash_two = build_params_hash(params)

    assert hash_one == hash_two
    assert len(hash_one) == 16

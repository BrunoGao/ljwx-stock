from datetime import date

from qlib_predict.app.feature_builder import build_dataset_config


def test_build_dataset_config_sets_test_segment() -> None:
    handler_config = {
        "dataset": {
            "class": "DatasetH",
            "module_path": "qlib.data.dataset",
            "kwargs": {
                "handler": {"class": "Alpha158"},
            },
        }
    }

    config = build_dataset_config(
        handler_config=handler_config, predict_day=date(2026, 3, 5)
    )
    kwargs = config.get("kwargs")
    assert isinstance(kwargs, dict)
    assert kwargs.get("segments") == {"test": ("2026-03-05", "2026-03-05")}

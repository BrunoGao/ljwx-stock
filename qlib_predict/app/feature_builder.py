from __future__ import annotations

from datetime import date
from typing import Mapping

import numpy as np
import pandas as pd


def set_predict_segment(
    dataset_config: Mapping[str, object],
    predict_day: date,
) -> dict[str, object]:
    config_copy = dict(dataset_config)
    kwargs_raw = config_copy.get("kwargs")
    kwargs = dict(kwargs_raw) if isinstance(kwargs_raw, dict) else {}

    predict_day_text = predict_day.isoformat()
    kwargs["segments"] = {"test": (predict_day_text, predict_day_text)}
    config_copy["kwargs"] = kwargs
    return config_copy


def build_dataset_config(
    handler_config: Mapping[str, object],
    predict_day: date,
) -> dict[str, object]:
    dataset_raw = handler_config.get("dataset")
    if isinstance(dataset_raw, dict):
        return set_predict_segment(dataset_raw, predict_day)

    return {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": dict(handler_config),
            "segments": {"test": (predict_day.isoformat(), predict_day.isoformat())},
        },
    }


def build_feature_frame(
    handler_config: Mapping[str, object],
    predict_day: date,
) -> pd.DataFrame:
    from qlib.data.dataset.handler import DataHandlerLP
    from qlib.utils import init_instance_by_config

    dataset_config = build_dataset_config(handler_config, predict_day)
    dataset = init_instance_by_config(dataset_config)

    feature_df = dataset.prepare("test", col_set="feature", data_key=DataHandlerLP.DK_I)
    if not isinstance(feature_df, pd.DataFrame):
        feature_df = pd.DataFrame(feature_df)

    feature_df = feature_df.replace([np.inf, -np.inf], np.nan)
    feature_df = feature_df.dropna(axis=0, how="all")
    if feature_df.empty:
        raise ValueError("预测特征为空，无法执行推理")

    fill_values = feature_df.median(axis=0, numeric_only=True)
    feature_df = feature_df.fillna(fill_values).fillna(0.0)

    return feature_df


__all__ = ["build_dataset_config", "build_feature_frame", "set_predict_segment"]

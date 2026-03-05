from __future__ import annotations

import json
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Mapping, TYPE_CHECKING

import joblib
import yaml

if TYPE_CHECKING:
    import pandas as pd


def build_params_hash(params: Mapping[str, object]) -> str:
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} 日期格式错误: {value}") from exc


def _extract_label_series(label_frame: pd.DataFrame | pd.Series) -> pd.Series:
    import pandas as pd

    if isinstance(label_frame, pd.Series):
        return label_frame

    if isinstance(label_frame, pd.DataFrame):
        if label_frame.shape[1] == 0:
            raise RuntimeError("标签数据为空")
        return label_frame.iloc[:, 0]

    raise RuntimeError("标签数据类型无效")


def _split_dates(start_day: date, end_day: date) -> tuple[date, date]:
    total_days = (end_day - start_day).days
    if total_days < 720:
        raise RuntimeError("训练窗口过短，至少需要 720 个日历日")

    train_end = start_day + timedelta(days=int(total_days * 0.70))
    valid_end = start_day + timedelta(days=int(total_days * 0.85))

    if valid_end >= end_day:
        valid_end = end_day - timedelta(days=30)
    if train_end >= valid_end:
        train_end = valid_end - timedelta(days=30)

    if train_end <= start_day or valid_end <= train_end:
        raise RuntimeError("无法生成有效的训练/验证时间分段")

    return train_end, valid_end


def train_lightgbm(
    qlib_provider_uri: str,
    out_model_dir: str,
    end_date: str,
    horizon: int,
    *,
    lookback_years: int = 8,
    code_version: str = "unknown",
    model_name: str = "qlib_lightgbm_alpha158",
    region: str = "cn",
) -> dict[str, object]:
    import lightgbm as lgb
    import pandas as pd
    import qlib
    from qlib.data.dataset.handler import DataHandlerLP
    from qlib.utils import init_instance_by_config

    if horizon <= 0:
        raise ValueError("horizon 必须大于 0")

    end_day = _parse_date(end_date, "end_date")
    start_day = end_day - timedelta(days=lookback_years * 365)
    train_end, valid_end = _split_dates(start_day, end_day)

    label_expr = f"Ref($close, -{horizon}) / $close - 1"
    handler_config: dict[str, object] = {
        "class": "Alpha158",
        "module_path": "qlib.contrib.data.handler",
        "kwargs": {
            "start_time": start_day.isoformat(),
            "end_time": end_day.isoformat(),
            "fit_start_time": start_day.isoformat(),
            "fit_end_time": valid_end.isoformat(),
            "instruments": "all",
            "label": [label_expr],
        },
    }

    dataset_config: dict[str, object] = {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": handler_config,
            "segments": {
                "train": (start_day.isoformat(), train_end.isoformat()),
                "valid": (
                    (train_end + timedelta(days=1)).isoformat(),
                    valid_end.isoformat(),
                ),
                "test": (
                    (valid_end + timedelta(days=1)).isoformat(),
                    end_day.isoformat(),
                ),
            },
        },
    }

    qlib.init(provider_uri=qlib_provider_uri, region=region)
    dataset = init_instance_by_config(dataset_config)

    train_feature_raw = dataset.prepare(
        "train", col_set="feature", data_key=DataHandlerLP.DK_L
    )
    train_label_raw = dataset.prepare(
        "train", col_set="label", data_key=DataHandlerLP.DK_L
    )
    valid_feature_raw = dataset.prepare(
        "valid", col_set="feature", data_key=DataHandlerLP.DK_L
    )
    valid_label_raw = dataset.prepare(
        "valid", col_set="label", data_key=DataHandlerLP.DK_L
    )

    train_feature = (
        train_feature_raw
        if isinstance(train_feature_raw, pd.DataFrame)
        else pd.DataFrame(train_feature_raw)
    )
    valid_feature = (
        valid_feature_raw
        if isinstance(valid_feature_raw, pd.DataFrame)
        else pd.DataFrame(valid_feature_raw)
    )

    train_label = _extract_label_series(train_label_raw)
    valid_label = _extract_label_series(valid_label_raw)

    train_frame = train_feature.join(train_label.rename("label"), how="inner").dropna(
        axis=0, how="any"
    )
    valid_frame = valid_feature.join(valid_label.rename("label"), how="inner").dropna(
        axis=0, how="any"
    )

    if train_frame.empty:
        raise RuntimeError("训练集为空，无法训练模型")
    if valid_frame.empty:
        raise RuntimeError("验证集为空，无法训练模型")

    x_train = train_frame.drop(columns=["label"])
    y_train = train_frame["label"]
    x_valid = valid_frame.drop(columns=["label"])
    y_valid = valid_frame["label"]

    train_dataset = lgb.Dataset(x_train.to_numpy(), label=y_train.to_numpy(dtype=float))
    valid_dataset = lgb.Dataset(
        x_valid.to_numpy(), label=y_valid.to_numpy(dtype=float), reference=train_dataset
    )

    model_params: dict[str, object] = {
        "objective": "regression",
        "metric": "l2",
        "learning_rate": 0.05,
        "num_leaves": 63,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.9,
        "bagging_freq": 5,
        "seed": 20260304,
        "verbosity": -1,
    }

    booster = lgb.train(
        model_params,
        train_set=train_dataset,
        num_boost_round=400,
        valid_sets=[valid_dataset],
        valid_names=["valid"],
        callbacks=[lgb.early_stopping(stopping_rounds=40, verbose=False)],
    )

    model_date = end_day.strftime("%Y%m%d")
    family_root = Path(out_model_dir)
    artifact_dir = family_root / model_date
    artifact_dir.mkdir(parents=True, exist_ok=True)

    model_path = artifact_dir / "model.pkl"
    handler_path = artifact_dir / "handler_config.yaml"
    meta_path = artifact_dir / "meta.json"

    joblib.dump(booster, model_path)

    handler_output = {
        "featureset": "Alpha158",
        "label": label_expr,
        "dataset": dataset_config,
    }
    handler_path.write_text(
        yaml.safe_dump(handler_output, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    hash_params: dict[str, object] = {
        "provider_uri": qlib_provider_uri,
        "end_date": end_day.isoformat(),
        "horizon_days": horizon,
        "lookback_years": lookback_years,
        "region": region,
        "model": "lightgbm",
        "feature_set": "Alpha158",
    }
    params_hash = build_params_hash(hash_params)

    model_version = f"{model_name}_{model_date}"
    meta = {
        "model_version": model_version,
        "data_cutoff": end_day.isoformat(),
        "code_version": code_version,
        "params_hash": params_hash,
        "horizon_days": horizon,
        "provider_uri": qlib_provider_uri,
    }
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )

    latest_path = family_root / "LATEST"
    latest_path.write_text(f"{model_date}\n", encoding="utf-8")

    return {
        "model_date": model_date,
        "artifact_dir": str(artifact_dir),
        "model_pkl": str(model_path),
        "handler_config": str(handler_path),
        "meta_json": str(meta_path),
        "model_version": model_version,
        "params_hash": params_hash,
        "data_cutoff": end_day.isoformat(),
    }

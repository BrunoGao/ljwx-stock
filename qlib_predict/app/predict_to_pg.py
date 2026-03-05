import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Iterable

import joblib
import yaml

from .config import Settings, get_settings
from .db_writer import build_params_hash, write_reco_daily_rows
from .feature_builder import build_feature_frame
from .model_loader import MODEL_FAMILY, resolve_model_artifacts

STRATEGY_NAME = "qlib_lightgbm_v1"


def init_qlib(provider_uri: str) -> None:
    import qlib

    qlib.init(provider_uri=provider_uri, region="cn")


def _read_yaml(path: Path) -> dict[str, object]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"handler_config.yaml 格式无效: {path}")
    return raw


def _read_json(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"meta.json 格式无效: {path}")
    return raw


def _resolve_predict_date(predict_date_raw: str | None) -> date:
    if predict_date_raw is not None and predict_date_raw.strip() != "":
        try:
            return date.fromisoformat(predict_date_raw)
        except ValueError as exc:
            raise ValueError(f"PREDICT_DATE 格式错误: {predict_date_raw}") from exc

    from qlib.data import D

    calendar = D.calendar(start_time=None, end_time=None, freq="day")
    if len(calendar) == 0:
        raise ValueError("无法从 qlib 日历推导最近交易日")

    latest = calendar[-1]
    if hasattr(latest, "date"):
        return latest.date()  # type: ignore[return-value]
    return date.fromisoformat(str(latest)[:10])


def _extract_symbol(index_value: object) -> str:
    if isinstance(index_value, tuple) and len(index_value) >= 2:
        return str(index_value[1])
    return str(index_value)


def _search_first_value(data: object, keys: Iterable[str]) -> object | None:
    key_set = set(keys)
    if isinstance(data, dict):
        for key, value in data.items():
            if key in key_set:
                return value
            child_value = _search_first_value(value, keys)
            if child_value is not None:
                return child_value
    elif isinstance(data, list):
        for item in data:
            child_value = _search_first_value(item, keys)
            if child_value is not None:
                return child_value
    return None


def _resolve_model_version(meta: dict[str, object], model_date: str) -> str:
    raw = meta.get("model_version")
    if isinstance(raw, str) and raw.strip() != "":
        return raw
    return f"{MODEL_FAMILY}_{model_date}"


def run_prediction(settings: Settings, dry_run: bool = False) -> dict[str, object]:
    resolved = resolve_model_artifacts(
        model_root=settings.resolved_model_root,
        model_date_override=settings.qlib_model_date,
    )

    model_date = str(resolved["model_date"])
    artifact_dir = Path(str(resolved["artifact_dir"]))

    if dry_run:
        return {
            "status": "dry_run",
            "model_date": model_date,
            "artifact_dir": str(artifact_dir),
            "model_pkl": str(resolved["model_pkl"]),
            "handler_config": str(resolved["handler_config"]),
            "meta_json": str(resolved["meta_json"]),
            "provider_uri": settings.resolved_provider_uri,
            "model_root": settings.resolved_model_root,
            "predict_date": settings.resolved_predict_date,
        }

    init_qlib(settings.resolved_provider_uri)

    predict_day = _resolve_predict_date(settings.resolved_predict_date)
    handler_config = _read_yaml(Path(str(resolved["handler_config"])))
    meta_json = _read_json(Path(str(resolved["meta_json"])))

    feature_df = build_feature_frame(
        handler_config=handler_config, predict_day=predict_day
    )

    model = joblib.load(Path(str(resolved["model_pkl"])))
    raw_scores = model.predict(feature_df)

    if len(raw_scores) != len(feature_df.index):
        raise RuntimeError("模型预测结果长度与特征样本数不一致")

    scored_items: list[tuple[str, float]] = []
    for index_value, raw_score in zip(
        feature_df.index.tolist(), raw_scores, strict=True
    ):
        symbol = _extract_symbol(index_value)
        scored_items.append((symbol, float(raw_score)))

    scored_items.sort(key=lambda item: item[1], reverse=True)
    top_items = scored_items[: settings.candidate_pool_size]

    featureset_raw = _search_first_value(
        handler_config, ["featureset", "feature_set", "features"]
    )
    label_raw = _search_first_value(handler_config, ["label", "label_expr", "labels"])
    featureset = "unknown" if featureset_raw is None else str(featureset_raw)
    label = "unknown" if label_raw is None else str(label_raw)

    params = {
        "provider_uri": settings.resolved_provider_uri,
        "model_root": settings.resolved_model_root,
        "model_date": model_date,
        "predict_date": predict_day.isoformat(),
        "candidate_pool_size": settings.candidate_pool_size,
    }
    params_hash = build_params_hash(params)
    model_version = _resolve_model_version(meta_json, model_date)

    rows: list[dict[str, object]] = []
    for rank, (symbol, score) in enumerate(top_items, start=1):
        rows.append(
            {
                "symbol": symbol,
                "trade_date": predict_day,
                "strategy_name": STRATEGY_NAME,
                "score": score,
                "confidence": 0.5,
                "rank": rank,
                "reason_json": {
                    "model_date": model_date,
                    "provider_uri": settings.resolved_provider_uri,
                    "artifact_dir": str(artifact_dir),
                    "featureset": featureset,
                    "label": label,
                },
                "model_version": model_version,
                "data_cutoff": predict_day,
                "code_version": settings.code_version,
                "params_hash": params_hash,
            }
        )

    written_count = write_reco_daily_rows(settings.database_url, rows)
    return {
        "status": "ok",
        "strategy_name": STRATEGY_NAME,
        "model_date": model_date,
        "predict_date": predict_day.isoformat(),
        "candidate_count": len(rows),
        "written_count": written_count,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Qlib offline prediction writer")
    parser.add_argument(
        "--dry-run", action="store_true", help="Only validate model path resolving"
    )
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        settings = get_settings()
        result = run_prediction(settings=settings, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

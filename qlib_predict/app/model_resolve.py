from pathlib import Path

MODEL_FAMILY = "qlib_lightgbm_alpha158"


def _family_root(model_root: str) -> Path:
    return Path(model_root) / MODEL_FAMILY


def resolve_model_date(model_root: str, model_date_override: str | None) -> str:
    family_root = _family_root(model_root)
    if not family_root.exists():
        raise FileNotFoundError(f"模型目录不存在: {family_root}")

    if model_date_override is not None and model_date_override.strip() != "":
        date_dir = family_root / model_date_override
        if not date_dir.exists():
            raise FileNotFoundError(f"指定模型日期目录不存在: {date_dir}")
        return model_date_override

    latest_file = family_root / "LATEST"
    if not latest_file.exists():
        raise FileNotFoundError(f"模型版本文件缺失: {latest_file} (需要 LATEST)")

    latest_value = latest_file.read_text(encoding="utf-8").strip()
    if latest_value == "":
        raise ValueError(f"LATEST 内容为空: {latest_file}")

    date_dir = family_root / latest_value
    if not date_dir.exists():
        raise FileNotFoundError(f"LATEST 指向的模型目录不存在: {date_dir}")

    return latest_value


def resolve_artifact_dir(model_root: str, model_date: str) -> Path:
    artifact_dir = _family_root(model_root) / model_date
    if not artifact_dir.exists():
        raise FileNotFoundError(f"模型产物目录不存在: {artifact_dir}")
    return artifact_dir


def resolve_model_files(
    model_root: str, model_date_override: str | None
) -> dict[str, Path | str]:
    model_date = resolve_model_date(
        model_root=model_root, model_date_override=model_date_override
    )
    artifact_dir = resolve_artifact_dir(model_root=model_root, model_date=model_date)

    model_pkl = artifact_dir / "model.pkl"
    handler_config = artifact_dir / "handler_config.yaml"
    meta_json = artifact_dir / "meta.json"

    if not model_pkl.exists():
        raise FileNotFoundError(f"模型文件缺失: {model_pkl} (需要 model.pkl)")
    if not handler_config.exists():
        raise FileNotFoundError(
            f"特征配置缺失: {handler_config} (需要 handler_config.yaml)"
        )
    if not meta_json.exists():
        raise FileNotFoundError(f"模型元数据缺失: {meta_json} (需要 meta.json)")

    return {
        "model_date": model_date,
        "artifact_dir": artifact_dir,
        "model_pkl": model_pkl,
        "handler_config": handler_config,
        "meta_json": meta_json,
    }

from pathlib import Path

import pytest

from qlib_predict.app.model_resolve import (
    resolve_model_date,
    resolve_model_files,
)


def test_resolve_model_date_from_latest(tmp_path: Path) -> None:
    family_dir = tmp_path / "qlib_lightgbm_alpha158"
    family_dir.mkdir(parents=True)
    (family_dir / "LATEST").write_text("20240229\n", encoding="utf-8")
    (family_dir / "20240229").mkdir()

    resolved = resolve_model_date(model_root=str(tmp_path), model_date_override=None)
    assert resolved == "20240229"


def test_resolve_model_date_missing_latest_raises(tmp_path: Path) -> None:
    family_dir = tmp_path / "qlib_lightgbm_alpha158"
    family_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="LATEST"):
        resolve_model_date(model_root=str(tmp_path), model_date_override=None)


def test_resolve_model_files_missing_model_pkl_raises(tmp_path: Path) -> None:
    family_dir = tmp_path / "qlib_lightgbm_alpha158"
    artifact_dir = family_dir / "20240301"
    artifact_dir.mkdir(parents=True)
    (family_dir / "LATEST").write_text("20240301", encoding="utf-8")
    (artifact_dir / "handler_config.yaml").write_text("{}", encoding="utf-8")
    (artifact_dir / "meta.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="model.pkl"):
        resolve_model_files(model_root=str(tmp_path), model_date_override=None)

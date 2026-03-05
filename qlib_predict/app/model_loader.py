from __future__ import annotations

from pathlib import Path

from .model_resolve import MODEL_FAMILY, resolve_model_date, resolve_model_files


def resolve_latest_model_date(
    model_root: str,
    model_date_override: str | None,
) -> str:
    return resolve_model_date(
        model_root=model_root,
        model_date_override=model_date_override,
    )


def resolve_model_artifacts(
    model_root: str,
    model_date_override: str | None,
) -> dict[str, Path | str]:
    return resolve_model_files(
        model_root=model_root,
        model_date_override=model_date_override,
    )


__all__ = [
    "MODEL_FAMILY",
    "resolve_latest_model_date",
    "resolve_model_artifacts",
    "resolve_model_date",
    "resolve_model_files",
]

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from minio.error import S3Error

from .config import Settings, get_settings
from .dump_qlib_data import dump_qlib_data
from .export_raw_csv import export_raw_csv
from .preflight import preflight_or_raise
from .publish_minio import atomic_write_latest, create_minio_client, publish_to_minio
from .train_model import train_lightgbm


class PipelineError(RuntimeError):
    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Qlib bootstrap pipeline")
    parser.add_argument(
        "--preflight-only", action="store_true", help="仅执行数据库预检"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="仅输出执行计划，不执行导出/训练/发布"
    )
    return parser


def _resolve_train_end_date(
    settings: Settings, preflight_summary: dict[str, object]
) -> date:
    if settings.train_end_date is not None and settings.train_end_date.strip() != "":
        return date.fromisoformat(settings.train_end_date)

    max_trade_date_raw = preflight_summary.get("max_trade_date")
    if not isinstance(max_trade_date_raw, str) or max_trade_date_raw.strip() == "":
        raise PipelineError("预检返回缺少 max_trade_date，无法推导训练截止日期", 2)

    return date.fromisoformat(max_trade_date_raw)


def run(
    settings: Settings, preflight_only: bool, dry_run_flag: bool
) -> tuple[int, dict[str, object]]:
    try:
        preflight_summary = preflight_or_raise(settings.database_url)
    except RuntimeError as exc:
        raise PipelineError(str(exc), 2) from exc

    result: dict[str, object] = {"preflight": preflight_summary}

    if preflight_only:
        result["status"] = "preflight_ok"
        return 0, result

    train_end_day = _resolve_train_end_date(
        settings=settings, preflight_summary=preflight_summary
    )
    export_start_day = train_end_day - timedelta(
        days=settings.export_lookback_calendar_days
    )

    effective_dry_run = dry_run_flag or settings.dry_run
    if effective_dry_run:
        result["status"] = "dry_run"
        result["plan"] = {
            "export_start_date": export_start_day.isoformat(),
            "export_end_date": train_end_day.isoformat(),
            "output_root": settings.output_root,
            "model_name": settings.model_name,
            "horizon_days": settings.horizon_days,
            "lookback_years": settings.lookback_years,
        }
        return 0, result

    output_root = Path(settings.output_root)
    raw_dir = output_root / "raw"
    qlib_provider_dir = output_root / "qlib_data" / settings.qlib_region
    model_family_dir = output_root / "artifacts" / "models" / settings.model_name

    export_summary = export_raw_csv(
        pg_dsn=settings.database_url,
        out_dir=str(raw_dir),
        start_date=export_start_day.isoformat(),
        end_date=train_end_day.isoformat(),
    )
    result["export"] = export_summary

    dump_summary = dump_qlib_data(
        raw_dir=str(raw_dir),
        qlib_out_dir=str(qlib_provider_dir),
        region=settings.qlib_region,
    )
    result["dump"] = dump_summary

    train_summary = train_lightgbm(
        qlib_provider_uri=str(qlib_provider_dir),
        out_model_dir=str(model_family_dir),
        end_date=train_end_day.isoformat(),
        horizon=settings.horizon_days,
        lookback_years=settings.lookback_years,
        code_version=settings.code_version,
        model_name=settings.model_name,
        region=settings.qlib_region,
    )
    result["train"] = train_summary

    model_date_raw = train_summary.get("model_date")
    artifact_dir_raw = train_summary.get("artifact_dir")
    if not isinstance(model_date_raw, str) or model_date_raw.strip() == "":
        raise RuntimeError("训练结果缺少 model_date")
    if not isinstance(artifact_dir_raw, str) or artifact_dir_raw.strip() == "":
        raise RuntimeError("训练结果缺少 artifact_dir")

    model_date = model_date_raw
    artifact_dir = Path(artifact_dir_raw)

    try:
        qdata_publish = publish_to_minio(
            local_dir=str(qlib_provider_dir),
            minio_endpoint=settings.minio_endpoint,
            bucket=settings.minio_bucket,
            prefix=f"qlib_data/{settings.qlib_region}/{model_date}",
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
        )
        model_publish = publish_to_minio(
            local_dir=str(artifact_dir),
            minio_endpoint=settings.minio_endpoint,
            bucket=settings.minio_bucket,
            prefix=f"artifacts/models/{settings.model_name}/{model_date}",
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
        )

        minio_client = create_minio_client(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
        )
        atomic_write_latest(
            client=minio_client,
            bucket=settings.minio_bucket,
            latest_key=f"qlib_data/{settings.qlib_region}/LATEST",
            value=model_date,
        )
        atomic_write_latest(
            client=minio_client,
            bucket=settings.minio_bucket,
            latest_key=f"artifacts/models/{settings.model_name}/LATEST",
            value=model_date,
        )
    except (RuntimeError, ValueError, FileNotFoundError, OSError, S3Error) as exc:
        raise PipelineError(str(exc), 3) from exc

    result["publish"] = {
        "qdata": qdata_publish,
        "model": model_publish,
        "latest_qdata": f"qlib_data/{settings.qlib_region}/LATEST",
        "latest_model": f"artifacts/models/{settings.model_name}/LATEST",
    }
    result["status"] = "ok"
    return 0, result


def main() -> int:
    args = _build_arg_parser().parse_args()
    settings = get_settings()

    try:
        code, payload = run(
            settings=settings,
            preflight_only=args.preflight_only,
            dry_run_flag=args.dry_run,
        )
        print(json.dumps(payload, ensure_ascii=False))
        return code
    except PipelineError as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return exc.exit_code
    except (RuntimeError, ValueError, FileNotFoundError, OSError, S3Error) as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

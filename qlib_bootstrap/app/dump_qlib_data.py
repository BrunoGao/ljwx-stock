import subprocess
import sys
from pathlib import Path

_VENDORED_DUMP_SCRIPT = Path(__file__).resolve().parent / "vendor" / "qlib_dump_bin.py"


def _build_dump_command(features_dir: Path, output_dir: Path) -> list[str]:
    if not _VENDORED_DUMP_SCRIPT.exists():
        raise FileNotFoundError(f"缺少 qlib dump 脚本: {_VENDORED_DUMP_SCRIPT}")

    return [
        sys.executable,
        str(_VENDORED_DUMP_SCRIPT),
        "dump_all",
        "--data_path",
        str(features_dir),
        "--qlib_dir",
        str(output_dir),
        "--freq",
        "day",
        "--include_fields",
        "open,high,low,close,volume,amount",
    ]


def dump_qlib_data(raw_dir: str, qlib_out_dir: str, region: str) -> dict[str, object]:
    features_dir = Path(raw_dir) / "features"
    if not features_dir.exists():
        raise FileNotFoundError(f"原始 CSV 目录不存在: {features_dir}")

    output_dir = Path(qlib_out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    command = _build_dump_command(features_dir=features_dir, output_dir=output_dir)

    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() if exc.stderr is not None else str(exc)
        raise RuntimeError(f"Qlib dump 失败: {message}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Qlib dump 超时（1800 秒）") from exc

    return {
        "region": region,
        "features_dir": str(features_dir),
        "qlib_out_dir": str(output_dir),
        "stdout": completed.stdout.strip(),
    }

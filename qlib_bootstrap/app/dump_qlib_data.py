import subprocess
import sys
from pathlib import Path


def dump_qlib_data(raw_dir: str, qlib_out_dir: str, region: str) -> dict[str, object]:
    features_dir = Path(raw_dir) / "features"
    if not features_dir.exists():
        raise FileNotFoundError(f"原始 CSV 目录不存在: {features_dir}")

    output_dir = Path(qlib_out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "qlib.scripts.dump_bin",
        "dump_all",
        "--csv_path",
        str(features_dir),
        "--qlib_dir",
        str(output_dir),
        "--freq",
        "day",
        "--include_fields",
        "open,high,low,close,volume,amount",
    ]

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

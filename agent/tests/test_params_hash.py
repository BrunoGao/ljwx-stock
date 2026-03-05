# ruff: noqa: E402

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.strategy.ensemble_v1 import compute_params_hash


def test_params_hash_stable() -> None:
    params = {
        "symbols": ["600519", "000001"],
        "start_date": "2024-01-01",
        "end_date": "2024-06-01",
        "adjust": "qfq",
        "lookback_days_calendar": 150,
        "min_amount_avg": "10000000",
    }

    hash_first = compute_params_hash(params)
    hash_second = compute_params_hash(params)

    assert hash_first == hash_second
    assert len(hash_first) == 16

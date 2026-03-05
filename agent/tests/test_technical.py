# ruff: noqa: E402

from decimal import Decimal
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.tools.technical import calculate_ma, calculate_rsi14


def test_ma_math() -> None:
    close_values = [Decimal(value) for value in range(10, 20)]

    ma5 = calculate_ma(close_values, 5)
    ma10 = calculate_ma(close_values, 10)

    assert ma5 == pytest.approx(17.0)
    assert ma10 == pytest.approx(14.5)


def test_rsi_edge() -> None:
    increasing = [Decimal(value) for value in range(1, 25)]
    decreasing = [Decimal(value) for value in range(25, 0, -1)]

    rsi_increasing = calculate_rsi14(increasing)
    rsi_decreasing = calculate_rsi14(decreasing)

    assert rsi_increasing is not None
    assert rsi_decreasing is not None
    assert rsi_increasing == pytest.approx(100.0, abs=1e-6)
    assert rsi_decreasing == pytest.approx(0.0, abs=1e-6)

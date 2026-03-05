# ruff: noqa: E402

from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.metrics import record_request, render_metrics


def _extract_counter_value(payload: str, status: str) -> float:
    pattern = re.compile(
        rf'^agent_requests_total\{{status="{status}"\}}\s+([0-9]+(?:\.[0-9]+)?)$',
        re.MULTILINE,
    )
    match = pattern.search(payload)
    if match is None:
        return 0.0
    return float(match.group(1))


def test_metrics_counter_increment_after_one_request() -> None:
    before_text = render_metrics().decode("utf-8")
    before_value = _extract_counter_value(before_text, "success")

    record_request(status="success", duration_seconds=0.05)

    after_text = render_metrics().decode("utf-8")
    after_value = _extract_counter_value(after_text, "success")

    assert after_value == before_value + 1

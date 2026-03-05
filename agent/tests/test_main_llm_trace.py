# ruff: noqa: E402

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import _build_llm_trace_label


def test_build_llm_trace_label_includes_fallback_reasons() -> None:
    trace = _build_llm_trace_label(
        planner_name="rule_based",
        requested_provider_name="claude_proxy",
        plan_fallback_reason="llm_plan_failed: relay unavailable",
        summarize_fallback_reason="AnthropicError: 500",
    )
    assert "planner=rule_based" in trace
    assert "requested=claude_proxy" in trace
    assert "plan_fallback=llm_plan_failed: relay unavailable" in trace
    assert "summarize_fallback=AnthropicError: 500" in trace

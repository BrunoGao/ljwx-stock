# ruff: noqa: E402

from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models import Plan
from app.planner_rule import build_rule_based_plan


def test_plan_step_invalid_depends_on_type_raises() -> None:
    with pytest.raises(ValidationError, match="valid integer"):
        Plan.model_validate(
            {
                "steps": [
                    {
                        "step_index": 1,
                        "tool_name": "query_kline",
                        "params": {"symbol": "AAPL"},
                        "depends_on": ["bad-type"],
                    }
                ]
            }
        )


def test_build_plan_qlib_keyword_uses_reco_query() -> None:
    plan = build_rule_based_plan("请给我今天的 qlib 模型推荐")
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "reco_query"


def test_build_plan_extract_symbol_without_word_boundary() -> None:
    plan = build_rule_based_plan("请查询股票000505最近一个交易日的行情")
    assert len(plan.steps) >= 1
    assert plan.steps[0].tool_name == "query_kline"
    assert plan.steps[0].params["symbol"] == "000505"

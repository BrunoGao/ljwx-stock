# ruff: noqa: E402

import asyncio
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.llm.base import LLMProvider
from app.models import Plan, PlanStep
from app.planner_rule import build_plan


class _HugeTokenProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "huge-token"

    @property
    def token_budget(self) -> int:
        return 999999

    async def count_tokens(self, text: str) -> int:
        _ = text
        return 100001

    async def plan(self, user_query: str, tools: list[object]) -> Plan:
        _ = (user_query, tools)
        return Plan(
            steps=[
                PlanStep(
                    step_index=1, tool_name="query_kline", params={"symbol": "600519"}
                )
            ]
        )

    async def summarize(
        self, context: str, tool_results: list[dict[str, object]]
    ) -> str:
        _ = (context, tool_results)
        return "summary"


class _FailPlanProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "fail-plan"

    @property
    def token_budget(self) -> int:
        return 50000

    async def count_tokens(self, text: str) -> int:
        _ = text
        return 100

    async def plan(self, user_query: str, tools: list[object]) -> Plan:
        _ = (user_query, tools)
        raise RuntimeError("planner down")

    async def summarize(
        self, context: str, tool_results: list[dict[str, object]]
    ) -> str:
        _ = (context, tool_results)
        return "summary"


def test_token_budget_fallback_to_rule_planner() -> None:
    provider = _HugeTokenProvider()
    result = asyncio.run(
        build_plan(
            user_query="请分析 600519",
            llm_provider=provider,
            max_tokens_per_run=50000,
        )
    )

    assert result.planner == "rule_based"
    assert result.fallback_reason == "token_budget_exceeded"
    assert result.token_count == 100001


def test_llm_plan_failure_fallback_to_rule_planner() -> None:
    provider = _FailPlanProvider()
    result = asyncio.run(
        build_plan(
            user_query="请分析 600519",
            llm_provider=provider,
            max_tokens_per_run=50000,
        )
    )

    assert result.planner == "rule_based"
    assert result.fallback_reason is not None
    assert "llm_plan_failed" in result.fallback_reason


def test_rule_plan_uses_reco_query_for_qlib_intent() -> None:
    provider = _FailPlanProvider()
    result = asyncio.run(
        build_plan(
            user_query="给我 qlib 推荐",
            llm_provider=provider,
            max_tokens_per_run=50000,
        )
    )

    assert result.plan.steps[0].tool_name == "reco_query"

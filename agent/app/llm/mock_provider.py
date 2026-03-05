from __future__ import annotations

import re

from app.llm.base import LLMProvider
from app.models import Plan, PlanStep
from app.tool_registry import ToolSpec

_SYMBOL_PATTERN = re.compile(r"(?<!\\d)(\\d{6})(?!\\d)")


class MockProvider(LLMProvider):
    def __init__(self, token_budget: int = 50000) -> None:
        self._token_budget = token_budget

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def token_budget(self) -> int:
        return self._token_budget

    async def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    async def plan(self, user_query: str, tools: list[ToolSpec]) -> Plan:
        _ = tools
        symbol_match = _SYMBOL_PATTERN.search(user_query)
        symbol = symbol_match.group(1) if symbol_match is not None else "600519"

        if any(
            keyword in user_query.lower() for keyword in ("qlib", "lightgbm", "reco")
        ):
            return Plan(
                steps=[
                    PlanStep(
                        step_index=1,
                        tool_name="reco_query",
                        params={
                            "trade_date": None,
                            "strategy_name": "qlib_lightgbm_v1",
                            "top_n": 20,
                        },
                    )
                ]
            )

        if "推荐" in user_query or "选股" in user_query:
            return Plan(
                steps=[
                    PlanStep(
                        step_index=1,
                        tool_name="strategy_ensemble_v1",
                        params={"symbols": [symbol], "end_date": None},
                    )
                ]
            )

        return Plan(
            steps=[
                PlanStep(
                    step_index=1,
                    tool_name="query_kline",
                    params={
                        "symbol": symbol,
                        "start_date": None,
                        "end_date": None,
                        "adjust": "qfq",
                    },
                )
            ]
        )

    async def summarize(
        self, context: str, tool_results: list[dict[str, object]]
    ) -> str:
        _ = context
        if len(tool_results) == 0:
            return "未获取到工具结果。"
        return f"已完成 {len(tool_results)} 个步骤，结果已生成。"

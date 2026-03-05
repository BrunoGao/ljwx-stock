from __future__ import annotations

from dataclasses import dataclass
import re

from app.llm.base import LLMProvider
from app.models import Plan, PlanStep
from app.tool_registry import ToolSpec, list_tools

_SYMBOL_PATTERN = re.compile(r"(?<!\d)(\d{6})(?!\d)")


@dataclass(frozen=True)
class PlanBuildResult:
    plan: Plan
    planner: str
    token_count: int
    fallback_reason: str | None = None


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    text_lower = text.lower()
    return any(keyword in text or keyword.lower() in text_lower for keyword in keywords)


def _search_symbol(user_query: str) -> str | None:
    match = _SYMBOL_PATTERN.search(user_query)
    if match is None:
        return None
    return match.group(1)


def _extract_symbol(user_query: str) -> str:
    symbol = _search_symbol(user_query)
    if symbol is None:
        return "600519"
    return symbol


def _build_market_params(user_query: str) -> dict[str, object]:
    return {
        "symbol": _extract_symbol(user_query),
        "start_date": None,
        "end_date": None,
        "adjust": "qfq",
    }


def _build_strategy_params(user_query: str) -> dict[str, object]:
    symbol = _search_symbol(user_query)
    if symbol is None:
        return {"symbols": None, "end_date": None}
    return {"symbols": [symbol], "end_date": None}


def build_rule_based_plan(user_query: str) -> Plan:
    normalized_query = user_query.strip()
    market_params = _build_market_params(normalized_query)
    qlib_intent = _contains_any(
        normalized_query,
        ("qlib", "模型预测", "模型推荐", "lightgbm", "reco", "reco_daily"),
    )
    steps: list[PlanStep] = []
    step_index = 1

    if _contains_any(normalized_query, ("走势", "行情", "K线", "k线")):
        steps.append(
            PlanStep(
                step_index=step_index,
                tool_name="query_kline",
                params=market_params,
            )
        )
        step_index += 1

    if _contains_any(normalized_query, ("指标", "均线", "RSI", "rsi")):
        depends = [step_index - 1] if step_index > 1 else None
        steps.append(
            PlanStep(
                step_index=step_index,
                tool_name="technical_indicators",
                params=market_params,
                depends_on=depends,
            )
        )
        step_index += 1

    if qlib_intent:
        depends = [step_index - 1] if step_index > 1 else None
        steps.append(
            PlanStep(
                step_index=step_index,
                tool_name="reco_query",
                params={
                    "trade_date": None,
                    "strategy_name": "qlib_lightgbm_v1",
                    "top_n": 20,
                },
                depends_on=depends,
            )
        )
    elif _contains_any(normalized_query, ("选股", "筛选", "找出", "推荐")):
        depends = [step_index - 1] if step_index > 1 else None
        steps.append(
            PlanStep(
                step_index=step_index,
                tool_name="strategy_ensemble_v1",
                params=_build_strategy_params(normalized_query),
                depends_on=depends,
            )
        )

    if len(steps) == 0:
        steps.append(
            PlanStep(
                step_index=1,
                tool_name="query_kline",
                params=market_params,
            )
        )

    return Plan(steps=steps)


def _validate_plan_tool_names(plan: Plan, tools: list[ToolSpec]) -> None:
    allowed_names = {tool.name for tool in tools}
    for step in plan.steps:
        if step.tool_name not in allowed_names:
            raise ValueError(f"LLM 规划使用了未注册工具: {step.tool_name}")


async def build_plan(
    user_query: str,
    llm_provider: LLMProvider | None,
    max_tokens_per_run: int,
) -> PlanBuildResult:
    if llm_provider is None:
        return PlanBuildResult(
            plan=build_rule_based_plan(user_query),
            planner="rule_based",
            token_count=0,
        )

    tools = list_tools()
    try:
        token_count = await llm_provider.count_tokens(user_query)
    except Exception as exc:
        return PlanBuildResult(
            plan=build_rule_based_plan(user_query),
            planner="rule_based",
            token_count=0,
            fallback_reason=f"token_count_failed: {exc}",
        )

    if token_count > max_tokens_per_run:
        return PlanBuildResult(
            plan=build_rule_based_plan(user_query),
            planner="rule_based",
            token_count=token_count,
            fallback_reason="token_budget_exceeded",
        )

    try:
        llm_plan = await llm_provider.plan(user_query=user_query, tools=tools)
        if len(llm_plan.steps) == 0:
            raise ValueError("LLM 返回空计划")
        _validate_plan_tool_names(llm_plan, tools)
        return PlanBuildResult(
            plan=llm_plan,
            planner=llm_provider.provider_name,
            token_count=token_count,
        )
    except Exception as exc:
        return PlanBuildResult(
            plan=build_rule_based_plan(user_query),
            planner="rule_based",
            token_count=token_count,
            fallback_reason=f"llm_plan_failed: {exc}",
        )

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator

from app.models import ToolExecutionResult
from app.strategy.ensemble_v1 import run_ensemble_v1
from app.tool_registry import list_tools, register_tool
from app.tools.query_kline import validate_symbol_6digits


class StrategyEnsembleParams(BaseModel):
    symbols: list[str] | None = None
    end_date: date | None = None

    model_config = ConfigDict(frozen=True)

    @field_validator("symbols")
    @classmethod
    def _validate_symbols(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        for symbol in value:
            validate_symbol_6digits(symbol)
        return value


async def strategy_ensemble_v1_handler(
    params: StrategyEnsembleParams,
) -> ToolExecutionResult:
    try:
        result = await run_ensemble_v1(symbols=params.symbols, end_date=params.end_date)
        return ToolExecutionResult(success=True, result=result)
    except ValueError as exc:
        return ToolExecutionResult(success=False, error=str(exc))
    except RuntimeError as exc:
        return ToolExecutionResult(success=False, error=f"策略执行失败: {exc}")


def register_strategy_tools() -> None:
    existing = {tool.name for tool in list_tools()}
    if "strategy_ensemble_v1" in existing:
        return

    @register_tool(
        name="strategy_ensemble_v1",
        description="Run strategy ensemble and write reco_daily outputs",
        param_model=StrategyEnsembleParams,
    )
    async def _strategy_ensemble_v1(params: BaseModel) -> ToolExecutionResult:
        parsed = StrategyEnsembleParams.model_validate(params.model_dump())
        return await strategy_ensemble_v1_handler(parsed)


__all__ = [
    "StrategyEnsembleParams",
    "register_strategy_tools",
    "strategy_ensemble_v1_handler",
]

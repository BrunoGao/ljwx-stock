from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, field_validator

from app.config import get_settings
from app.models import ToolExecutionResult
from app.tool_registry import list_tools, register_tool
from app.tools.query_kline import (
    QueryKlineParams,
    query_kline_handler,
    validate_symbol_6digits,
)


class TechnicalIndicatorsParams(BaseModel):
    symbol: str
    start_date: date | None = None
    end_date: date | None = None
    adjust: str = "qfq"

    model_config = ConfigDict(frozen=True)

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, value: str) -> str:
        return validate_symbol_6digits(value)

    @field_validator("adjust")
    @classmethod
    def _validate_adjust(cls, value: str) -> str:
        if value not in {"qfq", "hfq", "none"}:
            raise ValueError("adjust must be one of qfq/hfq/none")
        return value


def _to_decimal_list(close_values: list[object]) -> list[Decimal]:
    decimals: list[Decimal] = []
    for raw_value in close_values:
        if raw_value is None:
            continue
        try:
            decimals.append(Decimal(str(raw_value)))
        except (InvalidOperation, ValueError):
            continue
    return decimals


def calculate_ma(close_values: list[Decimal], period: int) -> float | None:
    if period <= 0 or len(close_values) < period:
        return None
    window = close_values[-period:]
    result = sum(window) / Decimal(period)
    return float(result)


def calculate_rsi14(close_values: list[Decimal]) -> float | None:
    period = 14
    if len(close_values) < period + 1:
        return None

    gains: list[Decimal] = []
    losses: list[Decimal] = []

    recent_values = close_values[-(period + 1) :]
    for index in range(1, len(recent_values)):
        delta = recent_values[index] - recent_values[index - 1]
        gains.append(delta if delta > 0 else Decimal("0"))
        losses.append(-delta if delta < 0 else Decimal("0"))

    avg_gain = sum(gains) / Decimal(period)
    avg_loss = sum(losses) / Decimal(period)

    if avg_loss == 0 and avg_gain == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0

    rs = avg_gain / avg_loss
    rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))
    return float(rsi)


def _build_interpretation(rsi14: float | None) -> str:
    if rsi14 is None:
        return "数据不足，无法计算完整 RSI14。"
    if rsi14 >= 70.0:
        return "RSI 偏高，短期可能过热。"
    if rsi14 <= 30.0:
        return "RSI 偏低，短期可能超卖。"
    return "RSI 处于中性区间。"


async def technical_indicators_handler(
    params: TechnicalIndicatorsParams,
) -> ToolExecutionResult:
    symbol = validate_symbol_6digits(params.symbol)
    settings = get_settings()

    kline_result = await query_kline_handler(
        QueryKlineParams(
            symbol=symbol,
            start_date=params.start_date,
            end_date=params.end_date,
            adjust=params.adjust,
            fields=["close"],
            limit=settings.kline_max_limit,
        )
    )
    if not kline_result.success:
        return ToolExecutionResult(success=False, error=kline_result.error)

    result_payload = kline_result.result
    rows_raw = result_payload.get("rows")
    if not isinstance(rows_raw, list) or len(rows_raw) == 0:
        return ToolExecutionResult(
            success=False, error="未查询到可用于指标计算的K线数据"
        )

    close_values_raw: list[object] = []
    asof_date = None
    for row in rows_raw:
        if isinstance(row, dict):
            close_values_raw.append(row.get("close"))
            asof_date = row.get("trade_date", asof_date)

    close_values = _to_decimal_list(close_values_raw)
    ma5 = calculate_ma(close_values, 5)
    ma10 = calculate_ma(close_values, 10)
    ma20 = calculate_ma(close_values, 20)
    rsi14 = calculate_rsi14(close_values)

    indicators = {
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "rsi14": rsi14,
    }

    return ToolExecutionResult(
        success=True,
        result={
            "symbol": symbol,
            "adjust": params.adjust,
            "asof_date": asof_date,
            "indicators": indicators,
            "interpretation": _build_interpretation(rsi14),
        },
    )


def register_technical_tools() -> None:
    existing = {tool.name for tool in list_tools()}

    if "technical_indicators" not in existing:

        @register_tool(
            name="technical_indicators",
            description="Calculate MA/RSI indicators for a single symbol",
            param_model=TechnicalIndicatorsParams,
        )
        async def _technical_indicators(params: BaseModel) -> ToolExecutionResult:
            parsed = TechnicalIndicatorsParams.model_validate(params.model_dump())
            return await technical_indicators_handler(parsed)


__all__ = [
    "TechnicalIndicatorsParams",
    "calculate_ma",
    "calculate_rsi14",
    "register_technical_tools",
    "technical_indicators_handler",
]

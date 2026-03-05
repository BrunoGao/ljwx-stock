from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import db
from app.config import get_settings
from app.models import ToolExecutionResult
from app.tool_registry import list_tools, register_tool


def _jsonable_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


class RecoQueryParams(BaseModel):
    trade_date: date | None = None
    strategy_name: str = "qlib_lightgbm_v1"
    top_n: int = Field(default=20)

    model_config = ConfigDict(frozen=True)

    @field_validator("strategy_name")
    @classmethod
    def _validate_strategy_name(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned == "":
            raise ValueError("strategy_name 不能为空")
        return cleaned

    @field_validator("top_n")
    @classmethod
    def _validate_top_n(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("top_n 必须为正整数")
        return min(value, 50)


async def _resolve_trade_date(
    strategy_name: str, requested_trade_date: date | None
) -> date | None:
    if requested_trade_date is not None:
        return requested_trade_date

    settings = get_settings()
    latest_value = await db.fetch_value(
        query="""
        SELECT max(trade_date)
        FROM market.reco_daily
        WHERE strategy_name = $1
        """,
        params=(strategy_name,),
        timeout_seconds=settings.kline_query_timeout_seconds,
    )
    if isinstance(latest_value, date):
        return latest_value
    return None


async def reco_query_handler(params: RecoQueryParams) -> ToolExecutionResult:
    settings = get_settings()
    effective_trade_date = await _resolve_trade_date(
        strategy_name=params.strategy_name,
        requested_trade_date=params.trade_date,
    )

    if effective_trade_date is None:
        return ToolExecutionResult(
            success=True,
            result={
                "trade_date": None,
                "strategy_name": params.strategy_name,
                "rows": [],
                "row_count": 0,
            },
        )

    records = await db.fetch_rows(
        query="""
        SELECT
            symbol,
            score,
            confidence,
            rank,
            reason_json,
            data_cutoff,
            code_version
        FROM market.reco_daily
        WHERE trade_date = $1
          AND strategy_name = $2
        ORDER BY score DESC NULLS LAST
        LIMIT $3
        """,
        params=(effective_trade_date, params.strategy_name, params.top_n),
        timeout_seconds=settings.kline_query_timeout_seconds,
    )

    rows: list[dict[str, object]] = []
    for record in records:
        row_map = dict(record)
        rows.append(
            {
                "symbol": str(row_map.get("symbol", "")),
                "score": _jsonable_value(row_map.get("score")),
                "confidence": _jsonable_value(row_map.get("confidence")),
                "rank": row_map.get("rank"),
                "reason_json": row_map.get("reason_json"),
                "data_cutoff": _jsonable_value(row_map.get("data_cutoff")),
                "code_version": row_map.get("code_version"),
            }
        )

    return ToolExecutionResult(
        success=True,
        result={
            "trade_date": effective_trade_date.isoformat(),
            "strategy_name": params.strategy_name,
            "rows": rows,
            "row_count": len(rows),
        },
    )


def register_reco_query_tools() -> None:
    existing = {tool.name for tool in list_tools()}
    if "reco_query" in existing:
        return

    @register_tool(
        name="reco_query",
        description="Query top reco_daily rows by date and strategy name",
        param_model=RecoQueryParams,
    )
    async def _reco_query(params: BaseModel) -> ToolExecutionResult:
        parsed = RecoQueryParams.model_validate(params.model_dump())
        return await reco_query_handler(parsed)


__all__ = ["RecoQueryParams", "reco_query_handler", "register_reco_query_tools"]

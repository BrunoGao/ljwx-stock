import logging
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Final, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import db
from app.config import get_settings
from app.models import ToolExecutionResult
from app.tool_registry import list_tools, register_tool

logger = logging.getLogger(__name__)

_ALLOWED_FIELDS_MAP: Final[dict[str, str]] = {
    "open": "k.open AS open",
    "high": "k.high AS high",
    "low": "k.low AS low",
    "close": "k.close AS close",
    "volume": "k.volume AS volume",
    "amount": "k.amount AS amount",
    "turnover": "k.turnover AS turnover",
    "amplitude": "k.amplitude AS amplitude",
    "pct_chg": "k.pct_chg AS pct_chg",
    "chg": "k.chg AS chg",
}
_DEFAULT_QUERY_FIELDS: Final[tuple[str, ...]] = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "turnover",
    "pct_chg",
)
_DEFAULT_BULK_FIELDS: Final[tuple[str, ...]] = (
    "close",
    "high",
    "low",
    "amount",
    "volume",
)
_SYMBOL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{6}$")


def validate_symbol_6digits(symbol: str) -> str:
    if _SYMBOL_PATTERN.fullmatch(symbol) is None:
        raise ValueError("symbol must be 6 digits")
    return symbol


def _jsonable_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _normalize_fields(
    requested_fields: list[str], default_fields: tuple[str, ...]
) -> list[str]:
    raw_fields = requested_fields if requested_fields else list(default_fields)
    normalized: list[str] = []

    for field in raw_fields:
        cleaned = field.strip()
        if cleaned not in _ALLOWED_FIELDS_MAP:
            raise ValueError(f"field '{cleaned}' not in allowed fields")
        if cleaned not in normalized:
            normalized.append(cleaned)

    return normalized


def _build_select_list(fields: list[str]) -> str:
    select_parts = [
        "k.symbol AS symbol",
        "k.trade_date AS trade_date",
        "k.adjust AS adjust",
    ]
    select_parts.extend(_ALLOWED_FIELDS_MAP[field] for field in fields)
    return ", ".join(select_parts)


def _to_row_output(
    row_map: Mapping[str, object], fields: list[str]
) -> dict[str, object]:
    row_output: dict[str, object] = {
        "symbol": str(row_map.get("symbol", "")),
        "trade_date": _jsonable_value(row_map.get("trade_date")),
        "adjust": str(row_map.get("adjust", "")),
    }
    for field in fields:
        row_output[field] = _jsonable_value(row_map.get(field))
    return row_output


class QueryKlineParams(BaseModel):
    symbol: str
    start_date: date | None = None
    end_date: date | None = None
    adjust: str = "qfq"
    fields: list[str] = Field(default_factory=lambda: list(_DEFAULT_QUERY_FIELDS))
    limit: int = 60

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

    @field_validator("limit")
    @classmethod
    def _validate_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("limit must be positive")
        return value


class QueryKlineBulkParams(BaseModel):
    symbols: list[str] | None = None
    start_date: date | None = None
    end_date: date | None = None
    adjust: str = "qfq"
    fields: list[str] = Field(default_factory=lambda: list(_DEFAULT_BULK_FIELDS))
    per_symbol_limit: int = 60

    model_config = ConfigDict(frozen=True)

    @field_validator("symbols")
    @classmethod
    def _validate_symbols(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        for symbol in value:
            validate_symbol_6digits(symbol)
        return value

    @field_validator("adjust")
    @classmethod
    def _validate_adjust(cls, value: str) -> str:
        if value not in {"qfq", "hfq", "none"}:
            raise ValueError("adjust must be one of qfq/hfq/none")
        return value

    @field_validator("per_symbol_limit")
    @classmethod
    def _validate_per_symbol_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("per_symbol_limit must be positive")
        return value


async def query_kline_handler(params: QueryKlineParams) -> ToolExecutionResult:
    settings = get_settings()
    effective_fields = _normalize_fields(params.fields, _DEFAULT_QUERY_FIELDS)

    if params.limit > settings.kline_max_limit:
        raise ValueError(f"limit exceeds KLINE_MAX_LIMIT {settings.kline_max_limit}")

    select_list = _build_select_list(effective_fields)
    query = f"""
        SELECT {select_list}
        FROM market.kline_daily AS k
        WHERE k.symbol = $1
          AND k.adjust = $2
          AND ($3::date IS NULL OR k.trade_date >= $3::date)
          AND ($4::date IS NULL OR k.trade_date <= $4::date)
        ORDER BY k.trade_date ASC
        LIMIT $5
    """
    records = await db.fetch_rows(
        query=query,
        params=(
            params.symbol,
            params.adjust,
            params.start_date,
            params.end_date,
            params.limit,
        ),
        timeout_seconds=settings.kline_query_timeout_seconds,
    )

    rows: list[dict[str, object]] = []
    for record in records:
        rows.append(_to_row_output(dict(record), effective_fields))

    return ToolExecutionResult(
        success=True,
        result={
            "symbol": params.symbol,
            "adjust": params.adjust,
            "row_count": len(rows),
            "rows": rows,
        },
    )


async def query_kline_bulk_handler(params: QueryKlineBulkParams) -> ToolExecutionResult:
    settings = get_settings()
    effective_fields = _normalize_fields(params.fields, _DEFAULT_BULK_FIELDS)

    has_symbols_filter = params.symbols is not None and len(params.symbols) > 0
    if (
        has_symbols_filter
        and params.symbols is not None
        and len(params.symbols) > settings.kline_bulk_max_symbols
    ):
        raise ValueError(f"too many symbols: {len(params.symbols)}")

    effective_per_symbol_limit = min(
        params.per_symbol_limit, settings.kline_bulk_per_symbol_limit
    )

    if has_symbols_filter:
        count_query = """
            SELECT count(*)
            FROM market.kline_daily AS k
            WHERE k.adjust = $1
              AND ($2::date IS NULL OR k.trade_date >= $2::date)
              AND ($3::date IS NULL OR k.trade_date <= $3::date)
              AND k.symbol = ANY($4::text[])
        """
        count_params: tuple[object, ...] = (
            params.adjust,
            params.start_date,
            params.end_date,
            params.symbols,
        )
    else:
        count_query = """
            SELECT count(*)
            FROM market.kline_daily AS k
            WHERE k.adjust = $1
              AND ($2::date IS NULL OR k.trade_date >= $2::date)
              AND ($3::date IS NULL OR k.trade_date <= $3::date)
        """
        count_params = (
            params.adjust,
            params.start_date,
            params.end_date,
        )

    count_value = await db.fetch_value(
        query=count_query,
        params=count_params,
        timeout_seconds=settings.kline_query_timeout_seconds,
    )
    total_rows_before_truncate = int(count_value) if isinstance(count_value, int) else 0
    row_cap_applied = total_rows_before_truncate > settings.kline_bulk_max_rows

    if row_cap_applied:
        logger.warning(
            "bulk 查询命中总量保护，已应用行数上限",
            extra={
                "total_rows_before_truncate": total_rows_before_truncate,
                "row_cap": settings.kline_bulk_max_rows,
            },
        )

    fetch_limit = min(total_rows_before_truncate, settings.kline_bulk_max_rows)
    if fetch_limit == 0:
        return ToolExecutionResult(
            success=True,
            result={
                "grouped": {},
                "meta": {
                    "total_rows_before_truncate": total_rows_before_truncate,
                    "total_symbols": 0,
                    "truncated": False,
                    "row_cap_applied": row_cap_applied,
                },
            },
        )

    select_list = _build_select_list(effective_fields)
    if has_symbols_filter:
        rows_query = f"""
            SELECT {select_list}
            FROM market.kline_daily AS k
            WHERE k.adjust = $1
              AND ($2::date IS NULL OR k.trade_date >= $2::date)
              AND ($3::date IS NULL OR k.trade_date <= $3::date)
              AND k.symbol = ANY($4::text[])
            ORDER BY k.symbol ASC, k.trade_date DESC
            LIMIT $5
        """
        rows_params: tuple[object, ...] = (
            params.adjust,
            params.start_date,
            params.end_date,
            params.symbols,
            fetch_limit,
        )
    else:
        rows_query = f"""
            SELECT {select_list}
            FROM market.kline_daily AS k
            WHERE k.adjust = $1
              AND ($2::date IS NULL OR k.trade_date >= $2::date)
              AND ($3::date IS NULL OR k.trade_date <= $3::date)
            ORDER BY k.symbol ASC, k.trade_date DESC
            LIMIT $4
        """
        rows_params = (
            params.adjust,
            params.start_date,
            params.end_date,
            fetch_limit,
        )

    records = await db.fetch_rows(
        query=rows_query,
        params=rows_params,
        timeout_seconds=settings.kline_query_timeout_seconds,
    )

    grouped_desc: dict[str, list[dict[str, object]]] = {}
    truncated_by_per_symbol = False

    for record in records:
        row_map = dict(record)
        symbol = str(row_map.get("symbol", ""))
        bucket = grouped_desc.setdefault(symbol, [])
        if len(bucket) >= effective_per_symbol_limit:
            truncated_by_per_symbol = True
            continue
        bucket.append(_to_row_output(row_map, effective_fields))

    grouped: dict[str, list[dict[str, object]]] = {}
    for symbol, rows_desc in grouped_desc.items():
        grouped[symbol] = list(reversed(rows_desc))

    returned_rows = sum(len(items) for items in grouped.values())
    truncated = truncated_by_per_symbol or total_rows_before_truncate > returned_rows

    return ToolExecutionResult(
        success=True,
        result={
            "grouped": grouped,
            "meta": {
                "total_rows_before_truncate": total_rows_before_truncate,
                "total_symbols": len(grouped),
                "truncated": truncated,
                "row_cap_applied": row_cap_applied,
            },
        },
    )


def register_query_kline_tools() -> None:
    existing = {tool.name for tool in list_tools()}

    if "query_kline" not in existing:

        @register_tool(
            name="query_kline",
            description="Query daily kline data for a single symbol",
            param_model=QueryKlineParams,
        )
        async def _query_kline(params: BaseModel) -> ToolExecutionResult:
            parsed = QueryKlineParams.model_validate(params.model_dump())
            return await query_kline_handler(parsed)

    if "query_kline_bulk" not in existing:

        @register_tool(
            name="query_kline_bulk",
            description="Query daily kline data for multiple symbols",
            param_model=QueryKlineBulkParams,
        )
        async def _query_kline_bulk(params: BaseModel) -> ToolExecutionResult:
            parsed = QueryKlineBulkParams.model_validate(params.model_dump())
            return await query_kline_bulk_handler(parsed)


__all__ = [
    "QueryKlineParams",
    "QueryKlineBulkParams",
    "query_kline_handler",
    "query_kline_bulk_handler",
    "register_query_kline_tools",
    "validate_symbol_6digits",
]

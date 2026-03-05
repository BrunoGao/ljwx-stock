import json
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import asyncpg
from asyncpg import Record

from app.config import Settings

if TYPE_CHECKING:
    from app.strategy.base import StrategyReco

_POOL: asyncpg.Pool | None = None


async def init_db_pool(settings: Settings) -> asyncpg.Pool:
    global _POOL
    _POOL = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        timeout=settings.db_pool_timeout_seconds,
        command_timeout=settings.db_command_timeout_seconds,
    )
    return _POOL


async def close_db_pool() -> None:
    global _POOL
    if _POOL is not None:
        await _POOL.close()
        _POOL = None


def _get_pool() -> asyncpg.Pool:
    if _POOL is None:
        raise RuntimeError("database pool is not initialized")
    return _POOL


async def create_run_log(run_id: UUID, session_id: str | None, user_query: str) -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO market.agent_run_log (run_id, session_id, user_query, status, total_tokens)
            VALUES ($1, $2, $3, 'running', 0)
            """,
            run_id,
            session_id,
            user_query,
            timeout=5.0,
        )


async def update_run_log_plan(run_id: UUID, plan_json: dict[str, object]) -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE market.agent_run_log
            SET plan_json = $2::jsonb
            WHERE run_id = $1
            """,
            run_id,
            json.dumps(plan_json),
            timeout=5.0,
        )


async def update_run_log_success(
    run_id: UUID,
    result_summary: str,
    total_tokens: int,
    llm_provider: str | None,
) -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE market.agent_run_log
            SET
                result_summary = $2,
                total_tokens = $3,
                llm_provider = $4,
                status = 'success',
                finished_at = now(),
                error_text = NULL
            WHERE run_id = $1
            """,
            run_id,
            result_summary,
            total_tokens,
            llm_provider,
            timeout=5.0,
        )


async def update_run_log_failed(run_id: UUID, error_text: str) -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE market.agent_run_log
            SET
                status = 'failed',
                finished_at = now(),
                error_text = $2
            WHERE run_id = $1
            """,
            run_id,
            error_text,
            timeout=5.0,
        )


async def update_run_log_safety_flag(run_id: UUID, safety_flag: bool) -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE market.agent_run_log
            SET safety_flag = $2
            WHERE run_id = $1
            """,
            run_id,
            safety_flag,
            timeout=5.0,
        )


async def insert_tool_call_log_start(
    run_id: UUID,
    step_index: int,
    tool_name: str,
    params_json: dict[str, object],
) -> int:
    pool = _get_pool()
    async with pool.acquire() as conn:
        tool_call_id = await conn.fetchval(
            """
            INSERT INTO market.tool_call_log (run_id, step_index, tool_name, params_json, status)
            VALUES ($1, $2, $3, $4::jsonb, 'running')
            RETURNING id
            """,
            run_id,
            step_index,
            tool_name,
            json.dumps(params_json),
            timeout=5.0,
        )

    if not isinstance(tool_call_id, int):
        raise RuntimeError("tool_call_log id generation failed")
    return tool_call_id


async def update_tool_call_log_end(
    id: int,
    status: str,
    latency_ms: int,
    result_json: dict[str, object] | None,
    error_text: str | None,
) -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        serialized_result = json.dumps(result_json) if result_json is not None else None
        await conn.execute(
            """
            UPDATE market.tool_call_log
            SET
                status = $2,
                latency_ms = $3,
                result_json = $4::jsonb,
                error_text = $5
            WHERE id = $1
            """,
            id,
            status,
            latency_ms,
            serialized_result,
            error_text,
            timeout=5.0,
        )


async def fetch_rows(
    query: str,
    params: tuple[object, ...],
    timeout_seconds: float,
) -> list[Record]:
    pool = _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params, timeout=timeout_seconds)
    return rows


async def fetch_value(
    query: str,
    params: tuple[object, ...],
    timeout_seconds: float,
) -> object:
    pool = _get_pool()
    async with pool.acquire() as conn:
        value = await conn.fetchval(query, *params, timeout=timeout_seconds)
    return value


async def execute_query(
    query: str,
    params: tuple[object, ...],
    timeout_seconds: float,
) -> str:
    pool = _get_pool()
    async with pool.acquire() as conn:
        status = await conn.execute(query, *params, timeout=timeout_seconds)
    return status


async def get_latest_trade_date(adjust: str) -> date:
    pool = _get_pool()
    async with pool.acquire() as conn:
        latest_trade_date = await conn.fetchval(
            """
            SELECT max(trade_date)
            FROM market.kline_daily
            WHERE adjust = $1
            """,
            adjust,
            timeout=5.0,
        )

    if not isinstance(latest_trade_date, date):
        raise ValueError(f"未找到 adjust={adjust} 的交易日数据")
    return latest_trade_date


def _decimal_to_float(value: Decimal) -> float:
    return float(value)


async def insert_reco_qc_log(
    trade_date: date,
    strategy_name: str,
    check_name: str,
    status: str,
    detail_json: dict[str, object],
    threshold_json: dict[str, object],
) -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO market.reco_qc_log (
                trade_date,
                strategy_name,
                check_name,
                status,
                detail_json,
                threshold_json
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            """,
            trade_date,
            strategy_name,
            check_name,
            status,
            json.dumps(detail_json, ensure_ascii=False),
            json.dumps(threshold_json, ensure_ascii=False),
            timeout=5.0,
        )


async def insert_reco_daily_rows(rows: list["StrategyReco"]) -> int:
    if len(rows) == 0:
        return 0

    pool = _get_pool()
    values: list[tuple[object, ...]] = []
    for row in rows:
        values.append(
            (
                row.symbol,
                row.trade_date,
                row.strategy_name,
                _decimal_to_float(row.score),
                _decimal_to_float(row.confidence),
                row.rank,
                json.dumps(row.reason_json),
                row.model_version,
                row.data_cutoff,
                row.code_version,
                row.params_hash,
            )
        )

    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO market.reco_daily (
                symbol,
                trade_date,
                strategy_name,
                score,
                confidence,
                rank,
                reason_json,
                model_version,
                data_cutoff,
                code_version,
                params_hash
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11
            )
            ON CONFLICT (symbol, trade_date, strategy_name) DO UPDATE SET
                score = EXCLUDED.score,
                confidence = EXCLUDED.confidence,
                rank = EXCLUDED.rank,
                reason_json = EXCLUDED.reason_json,
                model_version = EXCLUDED.model_version,
                data_cutoff = EXCLUDED.data_cutoff,
                code_version = EXCLUDED.code_version,
                params_hash = EXCLUDED.params_hash
            """,
            values,
            timeout=5.0,
        )

    return len(rows)

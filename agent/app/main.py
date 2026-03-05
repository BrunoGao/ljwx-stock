from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from anthropic import AnthropicError
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import ValidationError

from app import db
from app.auth import verify_api_key
from app.config import Settings, get_settings
from app.executor import PlanExecutionError, execute_plan_with_completed_steps
from app.llm import create_llm_provider
from app.llm.base import LLMProvider
from app.llm.mock_provider import MockProvider
from app.metrics import metrics_content_type, record_request, render_metrics
from app.models import (
    ChatRequest,
    ChatResponse,
    CompletedPlanStep,
    HealthResponse,
    Plan,
    QcRunRequest,
    QcRunResponse,
)
from app.planner_rule import build_plan
from app.qc.qc_runner import run_reco_qc
from app.rate_limit import RateLimiter
from app.safety import assess_user_query, within_token_budget
from app.structured_log import setup_logging
from app.synthesizer_template import synthesize_response
from app.tool_registry import register_builtin_tools

logger = logging.getLogger(__name__)


def _compact_reason_text(reason: str, max_length: int = 120) -> str:
    compact = " ".join(reason.split())
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 3]}..."


def _build_llm_trace_label(
    planner_name: str,
    requested_provider_name: str,
    plan_fallback_reason: str | None,
    summarize_fallback_reason: str | None,
) -> str:
    labels = [
        f"planner={planner_name}",
        f"requested={requested_provider_name}",
    ]

    if plan_fallback_reason is not None:
        labels.append(f"plan_fallback={_compact_reason_text(plan_fallback_reason)}")
    if summarize_fallback_reason is not None:
        labels.append(
            "summarize_fallback=" + _compact_reason_text(summarize_fallback_reason),
        )
    return ";".join(labels)


async def _resolve_resume_context(
    payload: ChatRequest,
) -> tuple[UUID, Plan, list[CompletedPlanStep]] | None:
    should_resume = payload.resume or payload.resume_run_id is not None
    if not should_resume:
        return None

    resumable_run: db.ResumableRun | None = None
    if payload.resume_run_id is not None:
        try:
            resume_run_uuid = UUID(payload.resume_run_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="resume_run_id 格式无效，必须是 UUID",
            ) from exc
        resumable_run = await db.fetch_resumable_run_by_id(run_id=resume_run_uuid)
    else:
        if payload.session_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="resume 模式需要 session_id 或 resume_run_id",
            )
        resumable_run = await db.fetch_latest_resumable_run_by_session(
            session_id=payload.session_id
        )

    if resumable_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到可恢复任务",
        )

    if payload.user_query != resumable_run.user_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="resume 模式要求 user_query 与历史任务完全一致",
        )

    try:
        plan = Plan.model_validate(resumable_run.plan_json)
    except ValidationError as exc:
        raise PlanExecutionError("历史计划无效，无法恢复") from exc

    completed_records = await db.fetch_successful_tool_steps(
        run_id=resumable_run.run_id
    )
    completed_steps = [
        CompletedPlanStep(
            step_index=record.step_index,
            tool_name=record.tool_name,
            result=record.result_json,
            meta={},
        )
        for record in completed_records
    ]
    return resumable_run.run_id, plan, completed_steps


async def _enforce_rate_limit(
    request: Request,
    api_key: str = Depends(verify_api_key),
) -> str:
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed = await limiter.allow_request(api_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded，超过每分钟请求上限",
        )
    return api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("Agent 服务启动")

    app.state.settings = settings
    app.state.rate_limiter = RateLimiter(settings.rate_limit_rpm)

    await db.init_db_pool(settings)
    register_builtin_tools()

    llm_provider: LLMProvider
    try:
        llm_provider = create_llm_provider(settings)
        logger.info(
            "LLM Provider 初始化成功", extra={"provider": llm_provider.provider_name}
        )
    except ValueError as exc:
        logger.warning(
            "LLM Provider 初始化失败，降级到 mock", extra={"error": str(exc)}
        )
        llm_provider = MockProvider(token_budget=settings.max_tokens_per_run)

    app.state.llm_provider = llm_provider

    try:
        yield
    finally:
        await db.close_db_pool()
        logger.info("Agent 服务关闭")


app = FastAPI(title="ljwx-stock-agent", version="0.1.0", lifespan=lifespan)


@app.get("/v1/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/metrics")
async def metrics_endpoint(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    if not settings.metrics_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="metrics 已禁用",
        )
    return Response(
        content=render_metrics(),
        media_type=metrics_content_type(),
    )


@app.post("/v1/qc/run", response_model=QcRunResponse)
async def run_qc(
    payload: QcRunRequest,
    request: Request,
    _api_key: str = Depends(_enforce_rate_limit),
) -> QcRunResponse:
    settings: Settings = request.app.state.settings
    if not settings.qc_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="QC 功能已禁用",
        )

    try:
        result = await run_reco_qc(
            trade_date=payload.trade_date,
            strategy_name=payload.strategy_name,
            top_n=payload.top_n,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"QC 执行失败: {exc}",
        ) from exc

    return QcRunResponse.model_validate(result)


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    _api_key: str = Depends(_enforce_rate_limit),
) -> ChatResponse:
    started_at = time.perf_counter()
    request_status = "error"

    settings: Settings = request.app.state.settings
    llm_provider: LLMProvider = request.app.state.llm_provider
    run_id: UUID = uuid4()
    run_log_created = False

    resumed_from_run_id: UUID | None = None
    completed_steps: list[CompletedPlanStep] = []
    plan: Plan
    planner_name: str
    requested_provider_name = llm_provider.provider_name
    plan_fallback_reason: str | None = None
    summarize_fallback_reason: str | None = None
    planner_token_count = 0
    try:
        safety_result = assess_user_query(
            user_query=payload.user_query,
            max_user_query_len=settings.max_user_query_len,
        )

        resume_context = await _resolve_resume_context(payload=payload)
        if resume_context is not None:
            resumed_from_run_id, plan, completed_steps = resume_context
            planner_name = f"resume:{resumed_from_run_id}"

        await db.create_run_log(
            run_id=run_id,
            session_id=payload.session_id,
            user_query=payload.user_query,
            resumed_from_run_id=resumed_from_run_id,
            resume_completed_steps=len(completed_steps),
        )
        run_log_created = True

        if resume_context is None:
            plan_result = await build_plan(
                user_query=safety_result.safe_query,
                llm_provider=llm_provider,
                max_tokens_per_run=settings.max_tokens_per_run,
            )
            if plan_result.fallback_reason is not None:
                plan_fallback_reason = plan_result.fallback_reason
                logger.warning(
                    "Planner 触发降级",
                    extra={
                        "run_id": str(run_id),
                        "fallback_reason": _compact_reason_text(
                            plan_result.fallback_reason
                        ),
                        "planner": plan_result.planner,
                        "requested_llm_provider": requested_provider_name,
                    },
                )
            plan = plan_result.plan
            planner_name = plan_result.planner
            planner_token_count = plan_result.token_count
        else:
            logger.info(
                "检测到可恢复任务，已启用续跑",
                extra={
                    "run_id": str(run_id),
                    "resumed_from_run_id": str(resumed_from_run_id),
                    "completed_steps": len(completed_steps),
                },
            )

        if safety_result.truncated:
            logger.warning(
                "用户输入超长，已截断",
                extra={
                    "run_id": str(run_id),
                    "max_user_query_len": settings.max_user_query_len,
                },
            )

        if safety_result.injection_detected:
            try:
                await db.update_run_log_safety_flag(run_id=run_id, safety_flag=True)
            except Exception as exc:
                logger.warning(
                    "写入 safety_flag 失败",
                    extra={"run_id": str(run_id), "error": str(exc)},
                )
            logger.warning(
                "检测到潜在注入指令",
                extra={
                    "run_id": str(run_id),
                    "matched_rules": list(safety_result.matched_rules),
                },
            )

        await db.update_run_log_plan(run_id=run_id, plan_json=plan.model_dump())

        execution_result = await execute_plan_with_completed_steps(
            run_id=run_id,
            plan=plan,
            completed_steps=completed_steps,
        )
        used_tools = execution_result.get("used_tools", [])
        step_results = execution_result.get("step_results", [])

        if not isinstance(used_tools, list) or not isinstance(step_results, list):
            raise PlanExecutionError("工具执行结果结构无效")

        result_payload = [item for item in step_results if isinstance(item, dict)]
        response_text = synthesize_response(
            user_query=safety_result.safe_query,
            used_tools=[str(item) for item in used_tools],
            step_results=result_payload,
        )

        llm_output_tokens = 0
        try:
            response_text = await llm_provider.summarize(
                context=safety_result.safe_query,
                tool_results=result_payload,
            )
            llm_output_tokens = await llm_provider.count_tokens(response_text)
        except (RuntimeError, ValueError, OSError, AnthropicError) as exc:
            summarize_fallback_reason = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "LLM 总结失败，使用模板总结",
                extra={
                    "run_id": str(run_id),
                    "error": _compact_reason_text(str(exc)),
                    "requested_llm_provider": requested_provider_name,
                },
            )

        total_tokens = planner_token_count + llm_output_tokens
        if not within_token_budget(
            total_tokens=total_tokens,
            max_tokens_per_run=settings.max_tokens_per_run,
        ):
            raise PlanExecutionError("token 超过单次上限")

        llm_trace_label = _build_llm_trace_label(
            planner_name=planner_name,
            requested_provider_name=requested_provider_name,
            plan_fallback_reason=plan_fallback_reason,
            summarize_fallback_reason=summarize_fallback_reason,
        )

        await db.update_run_log_success(
            run_id=run_id,
            result_summary=response_text[:500],
            total_tokens=total_tokens,
            llm_provider=llm_trace_label,
        )

        request_status = "success"
        logger.info(
            "处理请求成功",
            extra={"run_id": str(run_id), "llm_trace": llm_trace_label},
        )
        return ChatResponse(
            response_text=response_text,
            used_tools=[str(item) for item in used_tools],
            run_id=str(run_id),
            resumed_from_run_id=(
                str(resumed_from_run_id) if resumed_from_run_id is not None else None
            ),
        )
    except PlanExecutionError as exc:
        if run_log_created:
            await db.update_run_log_failed(run_id=run_id, error_text=str(exc))
        logger.error("执行计划失败", extra={"run_id": str(run_id), "error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"执行失败: {exc}",
        ) from exc
    except HTTPException as exc:
        if run_log_created:
            await db.update_run_log_failed(run_id=run_id, error_text=str(exc.detail))
        logger.warning(
            "请求参数校验失败",
            extra={"run_id": str(run_id), "status_code": exc.status_code},
        )
        raise
    except Exception as exc:
        if run_log_created:
            await db.update_run_log_failed(run_id=run_id, error_text=str(exc))
        logger.error("未预期错误", extra={"run_id": str(run_id), "error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务内部错误",
        ) from exc
    finally:
        record_request(
            status=request_status,
            duration_seconds=time.perf_counter() - started_at,
        )

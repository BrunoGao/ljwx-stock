from pydantic import BaseModel, ConfigDict, Field
from datetime import date


class ChatRequest(BaseModel):
    user_query: str = Field(min_length=1)
    session_id: str | None = None

    model_config = ConfigDict(frozen=True)


class ChatResponse(BaseModel):
    response_text: str
    used_tools: list[str] = Field(default_factory=list)
    run_id: str

    model_config = ConfigDict(frozen=True)


class HealthResponse(BaseModel):
    status: str

    model_config = ConfigDict(frozen=True)


class PlanStep(BaseModel):
    step_index: int = Field(ge=1)
    tool_name: str
    params: dict[str, object] = Field(default_factory=dict)
    depends_on: list[int] | None = None

    model_config = ConfigDict(frozen=True)


class Plan(BaseModel):
    steps: list[PlanStep] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class ToolExecutionResult(BaseModel):
    success: bool
    result: dict[str, object] = Field(default_factory=dict)
    error: str | None = None
    meta: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class QcRunRequest(BaseModel):
    trade_date: date | None = None
    strategy_name: str = Field(default="qlib_lightgbm_v1", min_length=1)
    top_n: int = Field(default=20, ge=1, le=50)

    model_config = ConfigDict(frozen=True)


class QcRunResponse(BaseModel):
    trade_date: str
    strategy_name: str
    checks: list[dict[str, object]] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

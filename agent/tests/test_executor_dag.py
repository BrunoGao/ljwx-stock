# ruff: noqa: E402

import asyncio
import time
from pathlib import Path
import sys
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import executor as executor_module
from app.executor import PlanExecutionError, execute_plan
from app.models import Plan, PlanStep, ToolExecutionResult
from app.tool_registry import clear_tools, register_tool


class _SleepParams(BaseModel):
    sleep_seconds: float = Field(default=0.0, ge=0.0)

    model_config = ConfigDict(frozen=True)


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    clear_tools()
    yield
    clear_tools()


@pytest.fixture(autouse=True)
def _mock_db(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"id": 0}

    async def fake_insert_tool_call_log_start(
        run_id,
        step_index: int,
        tool_name: str,
        params_json: dict[str, object],
    ) -> int:
        _ = (run_id, step_index, tool_name, params_json)
        state["id"] += 1
        return state["id"]

    async def fake_update_tool_call_log_end(
        id: int,
        status: str,
        latency_ms: int,
        result_json: dict[str, object] | None,
        error_text: str | None,
    ) -> None:
        _ = (id, status, latency_ms, result_json, error_text)

    monkeypatch.setattr(
        executor_module.db,
        "insert_tool_call_log_start",
        fake_insert_tool_call_log_start,
    )
    monkeypatch.setattr(
        executor_module.db, "update_tool_call_log_end", fake_update_tool_call_log_end
    )


def _register_sleep_tool(name: str) -> None:
    @register_tool(
        name=name, description=f"sleep tool {name}", param_model=_SleepParams
    )
    async def _handler(params: BaseModel) -> ToolExecutionResult:
        parsed = _SleepParams.model_validate(params.model_dump())
        await asyncio.sleep(parsed.sleep_seconds)
        return ToolExecutionResult(success=True, result={"slept": parsed.sleep_seconds})


def test_concurrent_steps_complete_faster_than_serial() -> None:
    _register_sleep_tool("sleep_a")
    _register_sleep_tool("sleep_b")

    plan = Plan(
        steps=[
            PlanStep(step_index=1, tool_name="sleep_a", params={"sleep_seconds": 0.2}),
            PlanStep(step_index=2, tool_name="sleep_b", params={"sleep_seconds": 0.2}),
        ]
    )

    started_at = time.perf_counter()
    result = asyncio.run(execute_plan(run_id=uuid4(), plan=plan))
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.35
    assert result["used_tools"] == ["sleep_a", "sleep_b"]
    assert len(result["step_results"]) == 2


def test_dag_cycle_detection() -> None:
    _register_sleep_tool("sleep_a")
    _register_sleep_tool("sleep_b")

    plan = Plan(
        steps=[
            PlanStep(
                step_index=1,
                tool_name="sleep_a",
                params={"sleep_seconds": 0.0},
                depends_on=[2],
            ),
            PlanStep(
                step_index=2,
                tool_name="sleep_b",
                params={"sleep_seconds": 0.0},
                depends_on=[1],
            ),
        ]
    )

    with pytest.raises(PlanExecutionError, match="计划步骤存在循环依赖"):
        asyncio.run(execute_plan(run_id=uuid4(), plan=plan))

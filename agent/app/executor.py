import asyncio
import time
from uuid import UUID

from app import db
from app.metrics import record_tool_call
from app.models import Plan, PlanStep
from app.safety import ensure_tool_allowed
from app.tool_registry import get_tool, list_tools


class PlanExecutionError(RuntimeError):
    pass


def _allowed_tool_names() -> set[str]:
    return {spec.name for spec in list_tools()}


def _index_steps(plan: Plan) -> dict[int, PlanStep]:
    indexed_steps: dict[int, PlanStep] = {}
    for step in plan.steps:
        if step.step_index in indexed_steps:
            raise PlanExecutionError(f"步骤索引重复: {step.step_index}")
        indexed_steps[step.step_index] = step
    return indexed_steps


def _build_dependency_graph(
    step_map: dict[int, PlanStep],
) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    unresolved_dependencies: dict[int, set[int]] = {}
    reverse_dependencies: dict[int, set[int]] = {
        step_index: set() for step_index in step_map
    }

    for step_index, step in step_map.items():
        dependencies = set(step.depends_on or [])
        if step_index in dependencies:
            raise PlanExecutionError(f"步骤 {step_index} 不能依赖自身")

        missing_dependencies = sorted(
            dep for dep in dependencies if dep not in step_map
        )
        if len(missing_dependencies) > 0:
            missing_text = ",".join(str(dep) for dep in missing_dependencies)
            raise PlanExecutionError(f"depends_on 引用的步骤不存在: {missing_text}")

        unresolved_dependencies[step_index] = dependencies
        for dependency in dependencies:
            reverse_dependencies[dependency].add(step_index)

    return unresolved_dependencies, reverse_dependencies


async def _execute_single_step(
    run_id: UUID,
    step: PlanStep,
    whitelist: set[str],
) -> dict[str, object]:
    tool_call_id = await db.insert_tool_call_log_start(
        run_id=run_id,
        step_index=step.step_index,
        tool_name=step.tool_name,
        params_json=step.params,
    )
    start = time.perf_counter()

    try:
        ensure_tool_allowed(step.tool_name, whitelist)
        spec = get_tool(step.tool_name)
        params_model = spec.param_model.model_validate(step.params)
        result = await spec.handler(params_model)
        latency_ms = int((time.perf_counter() - start) * 1000)

        if not result.success:
            raise PlanExecutionError(result.error or "工具执行失败")

        await db.update_tool_call_log_end(
            id=tool_call_id,
            status="success",
            latency_ms=latency_ms,
            result_json=result.result,
            error_text=None,
        )
        record_tool_call(tool_name=step.tool_name, status="success")

        return {
            "step_index": step.step_index,
            "tool_name": step.tool_name,
            "result": result.result,
            "meta": result.meta,
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        error_text = str(exc).strip() or "步骤执行失败"
        await db.update_tool_call_log_end(
            id=tool_call_id,
            status="failed",
            latency_ms=latency_ms,
            result_json=None,
            error_text=error_text,
        )
        record_tool_call(tool_name=step.tool_name, status="failed")

        if isinstance(exc, PlanExecutionError):
            raise
        raise PlanExecutionError(error_text) from exc


async def execute_plan(run_id: UUID, plan: Plan) -> dict[str, object]:
    whitelist = _allowed_tool_names()
    step_map = _index_steps(plan)

    if len(step_map) == 0:
        return {"used_tools": [], "step_results": []}

    unresolved_dependencies, reverse_dependencies = _build_dependency_graph(step_map)

    ready_step_indexes = sorted(
        step_index
        for step_index, dependencies in unresolved_dependencies.items()
        if len(dependencies) == 0
    )
    if len(ready_step_indexes) == 0:
        raise PlanExecutionError("计划步骤存在循环依赖")

    used_tools: list[str] = []
    step_results: list[dict[str, object]] = []
    completed_steps = 0

    while len(ready_step_indexes) > 0:
        current_batch_indexes = list(ready_step_indexes)
        ready_step_indexes = []
        current_batch = [step_map[step_index] for step_index in current_batch_indexes]

        batch_tasks = [
            asyncio.create_task(
                _execute_single_step(run_id=run_id, step=step, whitelist=whitelist)
            )
            for step in current_batch
        ]
        batch_outputs = await asyncio.gather(*batch_tasks, return_exceptions=True)

        step_execution_errors: list[PlanExecutionError] = []
        batch_success_results: list[dict[str, object]] = []
        for output in batch_outputs:
            if isinstance(output, Exception):
                if isinstance(output, PlanExecutionError):
                    step_execution_errors.append(output)
                else:
                    step_execution_errors.append(
                        PlanExecutionError(str(output).strip() or "步骤执行失败")
                    )
            else:
                batch_success_results.append(output)

        if len(step_execution_errors) > 0:
            raise step_execution_errors[0]

        batch_success_results.sort(key=lambda item: int(item["step_index"]))
        for success_result in batch_success_results:
            current_step_index = int(success_result["step_index"])
            used_tools.append(str(success_result["tool_name"]))
            step_results.append(success_result)
            completed_steps += 1

            for dependent_step in reverse_dependencies[current_step_index]:
                unresolved_dependencies[dependent_step].discard(current_step_index)
                if len(unresolved_dependencies[dependent_step]) == 0:
                    ready_step_indexes.append(dependent_step)

        ready_step_indexes.sort()

    if completed_steps != len(step_map):
        raise PlanExecutionError("计划步骤存在循环依赖")

    return {"used_tools": used_tools, "step_results": step_results}

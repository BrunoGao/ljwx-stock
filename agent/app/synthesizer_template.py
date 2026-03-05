from typing import Mapping


def _build_generic_table(step_results: list[dict[str, object]]) -> str:
    table_lines = [
        "| Step | Tool | Status | Note |",
        "| --- | --- | --- | --- |",
    ]

    for row in step_results:
        step_index = row.get("step_index", "-")
        tool_name = row.get("tool_name", "-")
        result = row.get("result", {})
        note_text = ""
        if isinstance(result, dict):
            note_text = str(result.get("summary", ""))
        table_lines.append(f"| {step_index} | {tool_name} | success | {note_text} |")

    if len(step_results) == 0:
        table_lines.append("| - | - | - | 未执行任何步骤 |")

    return "\n".join(table_lines)


def _extract_strategy_result(
    step_results: list[dict[str, object]],
) -> dict[str, object] | None:
    for row in step_results:
        result = row.get("result")
        if not isinstance(result, dict):
            continue
        if result.get("strategy_name") == "strategy_ensemble_v1":
            return result
        if isinstance(result.get("display_rows"), list):
            return result
    return None


def _build_strategy_table(strategy_result: Mapping[str, object]) -> str:
    display_rows_raw = strategy_result.get("display_rows")
    if not isinstance(display_rows_raw, list) or len(display_rows_raw) == 0:
        return "| Rank | Symbol | Score | Confidence |\n| --- | --- | --- | --- |\n| - | - | - | - |"

    table_lines = [
        "| Rank | Symbol | Score | Confidence |",
        "| --- | --- | --- | --- |",
    ]

    for row in display_rows_raw:
        if not isinstance(row, dict):
            continue
        table_lines.append(
            "| {rank} | {symbol} | {score:.4f} | {confidence:.4f} |".format(
                rank=int(row.get("rank", 0)),
                symbol=str(row.get("symbol", "")),
                score=float(row.get("score", 0.0)),
                confidence=float(row.get("confidence", 0.0)),
            )
        )

    return "\n".join(table_lines)


def synthesize_response(
    user_query: str,
    used_tools: list[str],
    step_results: list[dict[str, object]],
) -> str:
    strategy_result = _extract_strategy_result(step_results)

    if strategy_result is None:
        summary_line = (
            f"已完成请求“{user_query}”的占位分析，共执行 {len(used_tools)} 个工具："
            f"{', '.join(used_tools) if used_tools else '无'}。"
        )
        table_markdown = _build_generic_table(step_results)
    else:
        candidate_count = int(strategy_result.get("candidate_count", 0))
        display_count = int(strategy_result.get("display_count", 0))
        data_cutoff = str(strategy_result.get("data_cutoff", ""))
        summary_line = (
            f"已完成请求“{user_query}”的策略筛选，候选池 {candidate_count} 条，"
            f"当前展示前 {display_count} 条，数据截面 {data_cutoff}。"
        )
        table_markdown = _build_strategy_table(strategy_result)

    risk_section = (
        "风险提示：当前结果基于规则模型与历史数据计算，不应直接用于实盘交易决策。"
    )

    disclaimer_section = (
        "免责声明：本服务仅用于研究与开发验证，不构成任何投资建议。"
        "市场有风险，投资需谨慎。"
    )

    return "\n\n".join(
        [
            "## 摘要\n" + summary_line,
            "## Markdown 表格\n" + table_markdown,
            "## 风险提示\n" + risk_section,
            "## 免责声明\n" + disclaimer_section,
        ]
    )

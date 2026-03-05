from __future__ import annotations

from typing import Mapping


def _format_number(value: object, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{numeric:.{digits}f}{suffix}"


def _build_result_note(result: Mapping[str, object]) -> str:
    if "summary" in result and str(result["summary"]).strip() != "":
        return str(result["summary"])
    if "row_count" in result:
        return f"row_count={result['row_count']}"
    if "candidate_count" in result and "display_count" in result:
        return (
            f"candidate_count={result['candidate_count']}, "
            f"display_count={result['display_count']}"
        )
    return ""


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
            note_text = _build_result_note(result)
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


def _extract_kline_result(
    step_results: list[dict[str, object]],
) -> dict[str, object] | None:
    for row in step_results:
        if row.get("tool_name") != "query_kline":
            continue
        result = row.get("result")
        if isinstance(result, dict):
            return result
    return None


def _resolve_latest_kline_row(
    rows_raw: list[object],
) -> Mapping[str, object] | None:
    latest_row: Mapping[str, object] | None = None
    latest_trade_date = ""
    for item in rows_raw:
        if not isinstance(item, dict):
            continue
        trade_date_raw = item.get("trade_date")
        if trade_date_raw is None:
            continue
        trade_date = str(trade_date_raw)
        if trade_date.strip() == "":
            continue
        if trade_date >= latest_trade_date:
            latest_trade_date = trade_date
            latest_row = item
    return latest_row


def _build_kline_table(
    symbol: str,
    adjust: str,
    row_count: int,
    latest_row: Mapping[str, object] | None,
) -> str:
    table_lines = [
        "| Symbol | Adjust | Trade Date | Close | Pct Chg | Row Count |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if latest_row is None:
        table_lines.append(f"| {symbol} | {adjust} | N/A | N/A | N/A | {row_count} |")
        return "\n".join(table_lines)

    trade_date = str(latest_row.get("trade_date", "N/A"))
    close_text = _format_number(latest_row.get("close"), digits=2)
    pct_chg_text = _format_number(latest_row.get("pct_chg"), digits=2, suffix="%")
    table_lines.append(
        f"| {symbol} | {adjust} | {trade_date} | {close_text} | {pct_chg_text} | "
        f"{row_count} |",
    )
    return "\n".join(table_lines)


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
    kline_result = _extract_kline_result(step_results)
    strategy_result = _extract_strategy_result(step_results)

    if kline_result is not None:
        symbol = str(kline_result.get("symbol", ""))
        adjust = str(kline_result.get("adjust", ""))
        rows_raw = kline_result.get("rows")
        rows = rows_raw if isinstance(rows_raw, list) else []
        latest_row = _resolve_latest_kline_row(rows)
        row_count = int(kline_result.get("row_count", len(rows)))

        if latest_row is None:
            summary_line = (
                f"已完成请求“{user_query}”的行情查询，"
                f"股票 {symbol}（{adjust}）未查询到可用行情。"
            )
        else:
            trade_date = str(latest_row.get("trade_date", "N/A"))
            close_text = _format_number(latest_row.get("close"), digits=2)
            pct_chg_text = _format_number(
                latest_row.get("pct_chg"), digits=2, suffix="%"
            )
            summary_line = (
                f"已完成请求“{user_query}”的行情查询。"
                f"{symbol} 最近交易日 {trade_date}，收盘价 {close_text}，"
                f"涨跌幅 {pct_chg_text}。"
            )

        table_markdown = _build_kline_table(
            symbol=symbol,
            adjust=adjust,
            row_count=row_count,
            latest_row=latest_row,
        )
    elif strategy_result is None:
        summary_line = (
            f"已完成请求“{user_query}”的分析，共执行 {len(used_tools)} 个工具："
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

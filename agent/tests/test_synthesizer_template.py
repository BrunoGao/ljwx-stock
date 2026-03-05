# ruff: noqa: E402

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.synthesizer_template import synthesize_response


def test_synthesize_response_includes_latest_kline_fields() -> None:
    response = synthesize_response(
        user_query="请查询股票000505最近一个交易日",
        used_tools=["query_kline"],
        step_results=[
            {
                "step_index": 1,
                "tool_name": "query_kline",
                "result": {
                    "symbol": "000505",
                    "adjust": "qfq",
                    "row_count": 2,
                    "rows": [
                        {
                            "trade_date": "2026-03-04",
                            "close": 7.12,
                            "pct_chg": 0.51,
                        },
                        {
                            "trade_date": "2026-03-05",
                            "close": 7.23,
                            "pct_chg": 1.54,
                        },
                    ],
                },
            }
        ],
    )

    assert "000505 最近交易日 2026-03-05" in response
    assert "收盘价 7.23" in response
    assert "涨跌幅 1.54%" in response


def test_synthesize_response_handles_empty_kline_rows() -> None:
    response = synthesize_response(
        user_query="请查询股票600519最近一个交易日",
        used_tools=["query_kline"],
        step_results=[
            {
                "step_index": 1,
                "tool_name": "query_kline",
                "result": {
                    "symbol": "600519",
                    "adjust": "qfq",
                    "row_count": 0,
                    "rows": [],
                },
            }
        ],
    )

    assert "未查询到可用行情" in response
    assert "| 600519 | qfq | N/A | N/A | N/A | 0 |" in response

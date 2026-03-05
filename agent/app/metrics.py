from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REQUESTS_TOTAL = Counter(
    "agent_requests_total",
    "Total chat requests",
    labelnames=("status",),
)
REQUEST_DURATION_SECONDS = Histogram(
    "agent_request_duration_seconds",
    "Chat request latency in seconds",
)
TOOL_CALLS_TOTAL = Counter(
    "tool_calls_total",
    "Total tool calls",
    labelnames=("tool_name", "status"),
)
RECO_QC_STATUS = Gauge(
    "reco_qc_status",
    "Latest reco QC status by strategy/check (pass=0,warn=1,error=2)",
    labelnames=("strategy_name", "check_name"),
)

_STATUS_VALUE_MAP: dict[str, int] = {
    "pass": 0,
    "warn": 1,
    "error": 2,
}


def record_request(status: str, duration_seconds: float) -> None:
    REQUESTS_TOTAL.labels(status=status).inc()
    REQUEST_DURATION_SECONDS.observe(duration_seconds)


def record_tool_call(tool_name: str, status: str) -> None:
    TOOL_CALLS_TOTAL.labels(tool_name=tool_name, status=status).inc()


def set_reco_qc_status(strategy_name: str, check_name: str, status: str) -> None:
    value = _STATUS_VALUE_MAP.get(status, 2)
    RECO_QC_STATUS.labels(strategy_name=strategy_name, check_name=check_name).set(value)


def render_metrics() -> bytes:
    return generate_latest()


def metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST

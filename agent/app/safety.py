from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re


class ToolNotAllowedError(RuntimeError):
    def __init__(self, tool_name: str) -> None:
        super().__init__(f"tool not allowed: {tool_name}")
        self.tool_name = tool_name


_EN_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore instructions", re.compile(r"\bignore\s+instructions?\b", re.IGNORECASE)),
    ("system prompt", re.compile(r"\bsystem\s+prompt\b", re.IGNORECASE)),
    ("you are now", re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE)),
    ("forget previous", re.compile(r"\bforget\s+previous\b", re.IGNORECASE)),
)

_ZH_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("忽略前面", re.compile(r"忽略前面")),
    ("忘记上面", re.compile(r"忘记上面")),
    ("你现在是", re.compile(r"你现在是")),
    ("新的指令", re.compile(r"新的指令")),
    ("覆盖系统", re.compile(r"覆盖系统")),
)


@dataclass(frozen=True)
class QuerySafetyResult:
    safe_query: str
    truncated: bool
    injection_detected: bool
    matched_rules: tuple[str, ...]


def ensure_tool_allowed(tool_name: str, whitelist: Iterable[str]) -> None:
    if tool_name not in set(whitelist):
        raise ToolNotAllowedError(tool_name)


def within_token_budget(total_tokens: int, max_tokens_per_run: int) -> bool:
    return total_tokens <= max_tokens_per_run


def detect_prompt_injection(user_query: str) -> tuple[bool, tuple[str, ...]]:
    matched: list[str] = []

    for rule_name, pattern in _EN_INJECTION_PATTERNS:
        if pattern.search(user_query) is not None:
            matched.append(rule_name)

    for rule_name, pattern in _ZH_INJECTION_PATTERNS:
        if pattern.search(user_query) is not None:
            matched.append(rule_name)

    return len(matched) > 0, tuple(matched)


def assess_user_query(user_query: str, max_user_query_len: int) -> QuerySafetyResult:
    if max_user_query_len <= 0:
        raise ValueError("MAX_USER_QUERY_LEN 必须为正整数")

    truncated = len(user_query) > max_user_query_len
    safe_query = user_query[:max_user_query_len] if truncated else user_query
    injection_detected, matched_rules = detect_prompt_injection(safe_query)

    return QuerySafetyResult(
        safe_query=safe_query,
        truncated=truncated,
        injection_detected=injection_detected,
        matched_rules=matched_rules,
    )

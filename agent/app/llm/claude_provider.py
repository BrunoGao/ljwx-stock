from __future__ import annotations

import json

from anthropic import AsyncAnthropic

from app.llm.base import LLMProvider
from app.models import Plan
from app.tool_registry import ToolSpec


class ClaudeProvider(LLMProvider):
    def __init__(
        self,
        auth_token: str,
        base_url: str,
        model: str,
        token_budget: int,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> None:
        self._client = AsyncAnthropic(
            auth_token=auth_token,
            base_url=base_url,
            timeout=timeout_seconds,
        )
        self._model = model
        self._token_budget = token_budget
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens

    @property
    def provider_name(self) -> str:
        return "claude_proxy"

    @property
    def token_budget(self) -> int:
        return self._token_budget

    async def count_tokens(self, text: str) -> int:
        response = await self._client.messages.count_tokens(
            model=self._model,
            system="You are a planning assistant.",
            messages=[{"role": "user", "content": text}],
            timeout=self._timeout_seconds,
        )
        return int(response.input_tokens)

    @staticmethod
    def _extract_text(response: object) -> str:
        content_blocks = getattr(response, "content", [])
        parts: list[str] = []
        for block in content_blocks:
            block_type = getattr(block, "type", "")
            if block_type == "text":
                text = getattr(block, "text", "")
                if isinstance(text, str) and text.strip() != "":
                    parts.append(text)
        if len(parts) == 0:
            raise ValueError("Claude 返回内容为空")
        return "\n".join(parts)

    @staticmethod
    def _extract_json_payload(raw_text: str) -> dict[str, object]:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start < 0 or end < 0 or end <= start:
            raise ValueError("Claude 返回中未找到有效 JSON")
        payload = json.loads(raw_text[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("Claude 返回 JSON 结构无效")
        return payload

    @staticmethod
    def _render_tools_text(tools: list[ToolSpec]) -> str:
        lines: list[str] = []
        for tool in tools:
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)

    async def plan(self, user_query: str, tools: list[ToolSpec]) -> Plan:
        tool_text = self._render_tools_text(tools)
        prompt = (
            "Return ONLY a JSON object with shape: "
            "{'steps':[{'step_index':1,'tool_name':'...','params':{},'depends_on':[...]?}]} .\n"
            "step_index starts from 1 and must be unique.\n"
            f"Available tools:\n{tool_text}\n"
            f"User query:\n{user_query}"
        )

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_output_tokens,
            temperature=0,
            system="You are a strict planner. Output JSON only.",
            messages=[{"role": "user", "content": prompt}],
            timeout=self._timeout_seconds,
        )

        raw_text = self._extract_text(response)
        payload = self._extract_json_payload(raw_text)
        return Plan.model_validate(payload)

    async def summarize(
        self, context: str, tool_results: list[dict[str, object]]
    ) -> str:
        results_json = json.dumps(tool_results, ensure_ascii=False)
        prompt = (
            "请基于以下上下文生成简洁中文总结，不要编造。\n"
            f"用户问题: {context}\n"
            f"工具结果: {results_json}"
        )
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_output_tokens,
            temperature=0,
            system="你是股票分析助手，请输出中文摘要。",
            messages=[{"role": "user", "content": prompt}],
            timeout=self._timeout_seconds,
        )
        raw_text = self._extract_text(response)
        return raw_text.strip()

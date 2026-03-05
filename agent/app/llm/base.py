from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.models import Plan

if TYPE_CHECKING:
    from app.tool_registry import ToolSpec


class LLMProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def token_budget(self) -> int:
        raise NotImplementedError

    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        raise NotImplementedError

    @abstractmethod
    async def plan(self, user_query: str, tools: list[ToolSpec]) -> Plan:
        raise NotImplementedError

    @abstractmethod
    async def summarize(
        self, context: str, tool_results: list[dict[str, object]]
    ) -> str:
        raise NotImplementedError

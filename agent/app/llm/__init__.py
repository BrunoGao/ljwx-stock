from __future__ import annotations

from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.claude_provider import ClaudeProvider
from app.llm.mock_provider import MockProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider.strip().lower()
    if provider == "mock":
        return MockProvider(token_budget=settings.max_tokens_per_run)

    if provider == "claude":
        if (
            settings.anthropic_auth_token is None
            or settings.anthropic_auth_token.strip() == ""
        ):
            raise ValueError("LLM_PROVIDER=claude 时必须提供 ANTHROPIC_AUTH_TOKEN")

        return ClaudeProvider(
            auth_token=settings.anthropic_auth_token,
            base_url=settings.anthropic_base_url,
            model=settings.anthropic_model,
            token_budget=settings.max_tokens_per_run,
            timeout_seconds=settings.llm_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
        )

    raise ValueError(f"不支持的 LLM_PROVIDER: {settings.llm_provider}")


__all__ = ["LLMProvider", "create_llm_provider"]

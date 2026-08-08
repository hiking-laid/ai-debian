"""LLM provider factory: pick an implementation from config/secrets."""

from __future__ import annotations

from toddler_dinner.config import Secrets
from toddler_dinner.interfaces import LLMProvider
from toddler_dinner.providers.llm.anthropic import AnthropicLLMProvider
from toddler_dinner.providers.llm.base import OpenAICompatibleProvider
from toddler_dinner.providers.llm.copilot import CopilotLLMProvider
from toddler_dinner.providers.llm.openai import OpenAILLMProvider

__all__ = [
    "AnthropicLLMProvider",
    "CopilotLLMProvider",
    "OpenAICompatibleProvider",
    "OpenAILLMProvider",
    "build_llm_provider",
]


def build_llm_provider(secrets: Secrets) -> LLMProvider:
    provider = secrets.llm_provider.lower()
    if provider == "copilot":
        # Credential comes from TDP_COPILOT_TOKEN or the cached device-flow OAuth token
        # (run `toddler-dinner login-copilot`).
        return CopilotLLMProvider(
            model=secrets.llm_model,
            copilot_token=secrets.copilot_token,
            endpoint=secrets.llm_endpoint,
        )
    if provider == "openai":
        if not secrets.llm_api_key:
            raise RuntimeError("openai provider requires TDP_LLM_API_KEY")
        return OpenAILLMProvider(
            api_key=secrets.llm_api_key,
            model=secrets.llm_model,
            endpoint=secrets.llm_endpoint,
        )
    if provider == "anthropic":
        if not secrets.llm_api_key:
            raise RuntimeError("anthropic provider requires TDP_LLM_API_KEY")
        return AnthropicLLMProvider(
            api_key=secrets.llm_api_key,
            model=secrets.llm_model,
            endpoint=secrets.llm_endpoint,
        )
    raise ValueError(f"unknown llm_provider: {secrets.llm_provider!r}")

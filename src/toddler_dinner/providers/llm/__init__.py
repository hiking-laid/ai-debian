"""LLM provider factory: pick an implementation from config/secrets."""

from __future__ import annotations

from toddler_dinner.config import Secrets
from toddler_dinner.interfaces import LLMProvider
from toddler_dinner.providers.llm.anthropic import AnthropicLLMProvider
from toddler_dinner.providers.llm.azure import AzureOpenAIProvider, AzureResponsesProvider
from toddler_dinner.providers.llm.base import OpenAICompatibleProvider
from toddler_dinner.providers.llm.copilot import CopilotLLMProvider
from toddler_dinner.providers.llm.gemini import GeminiLLMProvider
from toddler_dinner.providers.llm.openai import OpenAILLMProvider

__all__ = [
    "AnthropicLLMProvider",
    "AzureOpenAIProvider",
    "AzureResponsesProvider",
    "CopilotLLMProvider",
    "GeminiLLMProvider",
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
    if provider == "azure":
        if not secrets.llm_api_key:
            raise RuntimeError("azure provider requires TDP_LLM_API_KEY")
        deployment = secrets.azure_deployment or secrets.llm_model
        if secrets.azure_api.lower() == "responses":
            return AzureResponsesProvider(
                api_key=secrets.llm_api_key,
                deployment=deployment,
                resource_endpoint=secrets.azure_endpoint,
                api_version=secrets.azure_api_version,
                endpoint=secrets.llm_endpoint,   # optional full /openai/responses URL override
            )
        return AzureOpenAIProvider(
            api_key=secrets.llm_api_key,
            deployment=deployment,
            resource_endpoint=secrets.azure_endpoint,
            api_version=secrets.azure_api_version,
            endpoint=secrets.llm_endpoint,   # optional full chat/completions URL override
        )
    if provider == "anthropic":
        if not secrets.llm_api_key:
            raise RuntimeError("anthropic provider requires TDP_LLM_API_KEY")
        return AnthropicLLMProvider(
            api_key=secrets.llm_api_key,
            model=secrets.llm_model,
            endpoint=secrets.llm_endpoint,
        )
    if provider == "gemini":
        if not secrets.llm_api_key:
            raise RuntimeError("gemini provider requires TDP_LLM_API_KEY")
        return GeminiLLMProvider(
            api_key=secrets.llm_api_key,
            model=secrets.llm_model,
            endpoint=secrets.llm_endpoint,
        )
    raise ValueError(f"unknown llm_provider: {secrets.llm_provider!r}")

"""OpenAI LLM provider (standard chat/completions)."""

from __future__ import annotations

import httpx

from toddler_dinner.providers.llm.base import OpenAICompatibleProvider

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


class OpenAILLMProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        endpoint: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            endpoint=endpoint or OPENAI_CHAT_URL,
            model=model,
            api_key=api_key,
            client=client,
        )

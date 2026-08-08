"""Anthropic LLM provider (Messages API — different shape from OpenAI)."""

from __future__ import annotations

import httpx

from toddler_dinner.interfaces import LLMProvider
from toddler_dinner.models import Recipe
from toddler_dinner.providers.llm.base import RECIPE_SYSTEM, parse_recipe

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicLLMProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        endpoint: str | None = None,
        client: httpx.Client | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint or ANTHROPIC_URL
        self.max_tokens = max_tokens
        self._client = client or httpx.Client(timeout=60)

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        resp = self._client.post(self.endpoint, json=payload, headers=self._headers())
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    def generate_recipe(self, prompt: str) -> Recipe:
        return parse_recipe(self.complete(RECIPE_SYSTEM, prompt))

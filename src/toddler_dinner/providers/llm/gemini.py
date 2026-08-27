"""Google Gemini LLM provider (Generative Language API — its own request/response shape)."""

from __future__ import annotations

import httpx

from toddler_dinner.interfaces import LLMProvider
from toddler_dinner.models import Recipe
from toddler_dinner.providers.llm.base import RECIPE_SYSTEM, parse_recipe

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiLLMProvider(LLMProvider):
    """Google Gemini via the Generative Language `generateContent` endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        endpoint: str | None = None,
        client: httpx.Client | None = None,
        temperature: float = 0.7,
    ) -> None:
        self.api_key = api_key
        self.model = model
        # Full URL override, else build the generateContent URL for the chosen model.
        self.endpoint = endpoint or f"{GEMINI_BASE}/models/{model}:generateContent"
        self.temperature = temperature
        self._client = client or httpx.Client(timeout=60)

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "x-goog-api-key": self.api_key}

    def complete(self, system: str, user: str) -> str:
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": self.temperature},
        }
        resp = self._client.post(self.endpoint, json=payload, headers=self._headers())
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    def generate_recipe(self, prompt: str) -> Recipe:
        return parse_recipe(self.complete(RECIPE_SYSTEM, prompt))

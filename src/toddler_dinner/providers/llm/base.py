"""Shared helpers for LLM providers: JSON extraction + recipe parsing + OpenAI-compatible base.

OpenAI and GitHub Copilot both speak the OpenAI `chat/completions` shape, so they share this
base. Anthropic uses a different request/response shape and lives in its own module.
"""

from __future__ import annotations

import json
import re

import httpx

from toddler_dinner.interfaces import LLMProvider
from toddler_dinner.models import Recipe

RECIPE_SYSTEM = (
    "You generate exactly one safe, age-appropriate toddler dinner recipe. "
    "Respond with ONLY a JSON object (no prose, no markdown fences) matching: "
    '{"title": str, "ingredients": [{"name": str, "quantity": number, "unit": str}], '
    '"equipment": [str], "steps": [str], "tips": [str], '
    '"nutrition": {"protein_g": number, "sodium_mg": number}, '
    '"min_age_months": int, "food_groups": {"vegetables": number, "protein": number, '
    '"grains": number, "dairy": number, "fruit": number}, "tags": [str]}. '
    "Avoid choking hazards, added salt/sugar, and honey. "
    "'equipment' is the list of cookware/tools the parent needs (e.g. 'medium saucepan', "
    "'steamer basket', 'blender'); short noun phrases, no quantities unless it matters. "
    "Write the steps for a busy parent who is a beginner cook — practical and self-contained, "
    "not chef shorthand. Every step must state: how to PREP each item (peel/trim, and the cut "
    "size, e.g. 'cut into 1 cm cubes'), the exact COOKING METHOD (e.g. pan-fry, boil, steam, "
    "bake), the HEAT level, an approximate TIME, and a DONENESS cue (e.g. 'until soft enough to "
    "mash with a fork'). Assume no prior knowledge. Include quantities of water/oil where used. "
    "Each step is a SINGLE action and must be no longer than 50 words. "
    "Finish by mashing/chopping to an age-appropriate soft texture and cooling to just warm "
    "before serving. Prefer 5-8 clear steps. "
    "'tips' is a short list of practical serving/storage/variation notes; each tip is one "
    "sentence no longer than 25 words."
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json(raw: str) -> dict:
    """Best-effort: strip markdown fences and isolate the outermost JSON object."""
    text = _FENCE_RE.sub("", raw).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in LLM response: {raw[:200]!r}")
    return json.loads(text[start : end + 1])


def parse_recipe(raw: str) -> Recipe:
    return Recipe.model_validate(extract_json(raw))


class OpenAICompatibleProvider(LLMProvider):
    """Base for any endpoint speaking OpenAI's chat/completions API (OpenAI, Copilot)."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
        temperature: float = 0.7,
    ) -> None:
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.extra_headers = extra_headers or {}
        self.temperature = temperature
        self._client = client or httpx.Client(timeout=60)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        resp = self._client.post(self.endpoint, json=payload, headers=self._headers())
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def generate_recipe(self, prompt: str) -> Recipe:
        return parse_recipe(self.complete(RECIPE_SYSTEM, prompt))

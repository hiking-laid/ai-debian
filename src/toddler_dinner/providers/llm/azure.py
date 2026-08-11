"""Azure OpenAI LLM providers.

Azure exposes two request/response shapes; pick with ``TDP_AZURE_API``:

- ``chat``  (default) — classic chat/completions. URL embeds the deployment:
      {resource}/openai/deployments/{deployment}/chat/completions?api-version=...
  Reuses the OpenAI-compatible base (messages in, choices[0].message.content out).

- ``responses`` — the newer Responses API (required by gpt-4.1/gpt-5-class models):
      {resource}/openai/responses?api-version=...
  Different shape: `instructions` + `input` in, an `output` array out. The deployment
  is passed in the body as `model`.

Both authenticate with the **`api-key`** header (not `Authorization: Bearer`).
"""

from __future__ import annotations

import httpx

from toddler_dinner.interfaces import LLMProvider
from toddler_dinner.models import Recipe
from toddler_dinner.providers.llm.base import (
    RECIPE_SYSTEM,
    OpenAICompatibleProvider,
    parse_recipe,
)

DEFAULT_API_VERSION = "2024-02-15-preview"


def _resource_base(resource_endpoint: str) -> str:
    """Normalise a resource endpoint to just the host base, tolerating pasted paths.

    Accepts e.g. ``https://x.openai.azure.com``, ``.../openai``, ``.../openai/v1`` and returns
    ``https://x.openai.azure.com`` so we never double up the ``/openai/...`` path.
    """
    base = resource_endpoint.rstrip("/")
    for suffix in ("/openai/v1", "/openai"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.rstrip("/")


class AzureOpenAIProvider(OpenAICompatibleProvider):
    """Azure chat/completions (deployment in the URL path)."""

    def __init__(
        self,
        *,
        api_key: str,
        deployment: str,
        resource_endpoint: str | None = None,
        api_version: str = DEFAULT_API_VERSION,
        endpoint: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        chat_url = endpoint  # full chat/completions URL override, if given
        if not chat_url:
            if not (resource_endpoint and deployment):
                raise RuntimeError(
                    "Azure OpenAI requires a resource endpoint + deployment "
                    "(TDP_AZURE_ENDPOINT + TDP_AZURE_DEPLOYMENT), or a full TDP_LLM_ENDPOINT."
                )
            chat_url = (
                f"{_resource_base(resource_endpoint)}/openai/deployments/{deployment}"
                f"/chat/completions?api-version={api_version}"
            )
        super().__init__(
            endpoint=chat_url,
            model=deployment,               # informational; Azure routes by the path
            api_key=None,                   # Azure uses the api-key header, not Bearer
            extra_headers={"api-key": api_key},
            client=client,
        )


def _extract_responses_text(data: dict) -> str:
    """Pull assistant text out of a Responses API payload (ignoring reasoning items)."""
    convenience = data.get("output_text")
    if isinstance(convenience, str) and convenience.strip():
        return convenience
    chunks: list[str] = []
    for item in data.get("output", []) or []:
        if item.get("type") == "message":
            for part in item.get("content", []) or []:
                if part.get("type") in ("output_text", "text") and part.get("text"):
                    chunks.append(part["text"])
    return "".join(chunks)


class AzureResponsesProvider(LLMProvider):
    """Azure Responses API (`/openai/responses`); deployment goes in the body as `model`."""

    def __init__(
        self,
        *,
        api_key: str,
        deployment: str,
        resource_endpoint: str | None = None,
        api_version: str = DEFAULT_API_VERSION,
        endpoint: str | None = None,
        client: httpx.Client | None = None,
        max_output_tokens: int = 4096,
    ) -> None:
        url = endpoint  # full responses URL override, if given
        if not url:
            if not resource_endpoint:
                raise RuntimeError(
                    "Azure Responses API requires TDP_AZURE_ENDPOINT (or a full TDP_LLM_ENDPOINT)."
                )
            url = f"{_resource_base(resource_endpoint)}/openai/responses?api-version={api_version}"
        self.endpoint = url
        self.model = deployment
        self.api_key = api_key
        self.max_output_tokens = max_output_tokens
        self._client = client or httpx.Client(timeout=120)

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "api-key": self.api_key}

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "instructions": system,
            "input": user,
            "max_output_tokens": self.max_output_tokens,
        }
        resp = self._client.post(self.endpoint, json=payload, headers=self._headers())
        resp.raise_for_status()
        return _extract_responses_text(resp.json())

    def generate_recipe(self, prompt: str) -> Recipe:
        return parse_recipe(self.complete(RECIPE_SYSTEM, prompt))

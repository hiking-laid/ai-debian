"""GitHub Copilot LLM provider.

Copilot's chat endpoint is OpenAI-compatible, but auth is two-step and unofficial:

  1. A short-lived *Copilot token* is required to call the chat API.
  2. It's obtained by exchanging a GitHub token at the internal token endpoint; the response
     includes the token and an `expires_at`, so we cache and refresh it.

You can instead supply a pre-obtained Copilot token via TDP_COPILOT_TOKEN to skip the exchange.

NOTE: This uses GitHub's *internal* Copilot endpoints, which are undocumented and not an
officially supported general-purpose API. Availability and Terms-of-Service compliance are
your responsibility.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

from toddler_dinner.providers.llm.base import OpenAICompatibleProvider
from toddler_dinner.providers.llm.github_auth import DEFAULT_TOKEN_PATH, load_oauth_token

COPILOT_CHAT_URL = "https://api.githubcopilot.com/chat/completions"
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"

# Editor-identifying headers Copilot expects.
COPILOT_HEADERS = {
    "Editor-Version": "vscode/1.95.0",
    "Editor-Plugin-Version": "copilot-chat/0.22.0",
    "Copilot-Integration-Id": "vscode-chat",
    "User-Agent": "GitHubCopilotChat/0.22.0",
}

# Refresh the Copilot token this many seconds before it actually expires.
_REFRESH_BUFFER_S = 60


class CopilotLLMProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        *,
        model: str,
        github_token: str | None = None,
        copilot_token: str | None = None,
        endpoint: str | None = None,
        client: httpx.Client | None = None,
        oauth_token_path: Path | None = DEFAULT_TOKEN_PATH,
    ) -> None:
        super().__init__(
            endpoint=endpoint or COPILOT_CHAT_URL,
            model=model,
            api_key=None,  # set dynamically per request via _headers()
            extra_headers=COPILOT_HEADERS,
            client=client,
        )
        # Fall back to a cached device-flow OAuth token when no explicit credential is given.
        if not github_token and not copilot_token and oauth_token_path is not None:
            github_token = load_oauth_token(oauth_token_path)
        self._github_token = github_token
        self._copilot_token = copilot_token
        # 0 = unknown expiry. A statically-supplied token is treated as non-expiring.
        self._expires_at = 0.0
        self._static_token = copilot_token is not None and github_token is None

    def _ensure_token(self) -> None:
        if self._static_token:
            return
        fresh = self._copilot_token and time.time() < self._expires_at - _REFRESH_BUFFER_S
        if fresh:
            return
        if not self._github_token:
            raise RuntimeError(
                "Copilot needs a credential. Run `toddler-dinner login-copilot` (device flow), "
                "or set TDP_GITHUB_TOKEN / TDP_COPILOT_TOKEN."
            )
        resp = self._client.get(
            COPILOT_TOKEN_URL,
            headers={"Authorization": f"token {self._github_token}", **COPILOT_HEADERS},
        )
        resp.raise_for_status()
        data = resp.json()
        self._copilot_token = data["token"]
        self._expires_at = float(data.get("expires_at", 0))

    def _headers(self) -> dict[str, str]:
        self._ensure_token()
        headers = super()._headers()
        headers["Authorization"] = f"Bearer {self._copilot_token}"
        return headers

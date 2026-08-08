"""LLM provider tests using a fake httpx client (no real network)."""

from __future__ import annotations

import json

import pytest

from toddler_dinner.config import Secrets
from toddler_dinner.providers.llm import build_llm_provider
from toddler_dinner.providers.llm.anthropic import AnthropicLLMProvider
from toddler_dinner.providers.llm.base import OpenAICompatibleProvider, extract_json
from toddler_dinner.providers.llm.copilot import CopilotLLMProvider
from toddler_dinner.providers.llm.openai import OpenAILLMProvider


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeClient:
    """Records requests and returns queued responses in order."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.posts: list[dict] = []
        self.gets: list[dict] = []

    def post(self, url, json=None, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        return FakeResponse(self._responses.pop(0))

    def get(self, url, headers=None):
        self.gets.append({"url": url, "headers": headers})
        return FakeResponse(self._responses.pop(0))


def _chat_reply(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


RECIPE_JSON = json.dumps(
    {
        "title": "salmon rice",
        "ingredients": [{"name": "salmon", "quantity": 100, "unit": "g"}],
        "steps": ["steam"],
        "nutrition": {"protein_g": 9, "sodium_mg": 100},
        "min_age_months": 12,
        "food_groups": {"protein": 0.4, "grains": 1.0},
        "tags": ["fish"],
    }
)


# --- helpers ----------------------------------------------------------------

def test_extract_json_strips_fences_and_prose():
    raw = "Here you go:\n```json\n{\"a\": 1}\n```\nThanks!"
    assert extract_json(raw) == {"a": 1}


def test_extract_json_raises_without_object():
    with pytest.raises(ValueError):
        extract_json("no json here")


# --- OpenAI-compatible ------------------------------------------------------

def test_openai_complete_builds_request_and_parses():
    client = FakeClient([_chat_reply("hello")])
    p = OpenAICompatibleProvider(
        endpoint="https://x/chat", model="gpt-4o", api_key="sk-test", client=client
    )
    assert p.complete("sys", "usr") == "hello"
    sent = client.posts[0]
    assert sent["json"]["model"] == "gpt-4o"
    assert sent["json"]["messages"][0] == {"role": "system", "content": "sys"}
    assert sent["headers"]["Authorization"] == "Bearer sk-test"


def test_generate_recipe_parses_model_json():
    client = FakeClient([_chat_reply(RECIPE_JSON)])
    p = OpenAILLMProvider(api_key="sk", model="gpt-4o", client=client)
    recipe = p.generate_recipe("make dinner")
    assert recipe.title == "salmon rice"
    assert recipe.ingredients[0].name == "salmon"


# --- Copilot token exchange -------------------------------------------------

def test_copilot_exchanges_github_token_then_calls_chat():
    # 1st response = token exchange (GET), 2nd = chat completion (POST)
    client = FakeClient([
        {"token": "copilot-abc", "expires_at": 9999999999},
        _chat_reply("hi"),
    ])
    p = CopilotLLMProvider(model="gpt-4o", github_token="ghp_x", client=client)
    assert p.complete("s", "u") == "hi"
    assert client.gets[0]["url"].endswith("/copilot_internal/v2/token")
    assert client.gets[0]["headers"]["Authorization"] == "token ghp_x"
    # chat call uses the exchanged Copilot token
    assert client.posts[0]["headers"]["Authorization"] == "Bearer copilot-abc"
    assert client.posts[0]["headers"]["Copilot-Integration-Id"] == "vscode-chat"


def test_copilot_static_token_skips_exchange():
    client = FakeClient([_chat_reply("hi")])
    p = CopilotLLMProvider(model="gpt-4o", copilot_token="ct-123", client=client)
    assert p.complete("s", "u") == "hi"
    assert client.gets == []  # no exchange performed
    assert client.posts[0]["headers"]["Authorization"] == "Bearer ct-123"


def test_copilot_without_credentials_raises(tmp_path):
    client = FakeClient([])
    # point at a non-existent cache so no token is loaded
    p = CopilotLLMProvider(model="gpt-4o", client=client, oauth_token_path=tmp_path / "none.json")
    with pytest.raises(RuntimeError):
        p.complete("s", "u")


# --- Anthropic --------------------------------------------------------------

def test_anthropic_uses_messages_shape():
    client = FakeClient([{"content": [{"text": "hey"}]}])
    p = AnthropicLLMProvider(api_key="ak", model="claude-3", client=client)
    assert p.complete("sys", "usr") == "hey"
    sent = client.posts[0]
    assert sent["json"]["system"] == "sys"
    assert sent["json"]["messages"][0] == {"role": "user", "content": "usr"}
    assert sent["headers"]["x-api-key"] == "ak"


# --- factory ----------------------------------------------------------------

def test_factory_selects_provider():
    assert isinstance(
        build_llm_provider(Secrets(llm_provider="copilot", copilot_token="t")),
        CopilotLLMProvider,
    )
    assert isinstance(
        build_llm_provider(Secrets(llm_provider="openai", llm_api_key="k")),
        OpenAILLMProvider,
    )
    assert isinstance(
        build_llm_provider(Secrets(llm_provider="anthropic", llm_api_key="k")),
        AnthropicLLMProvider,
    )


def test_factory_rejects_unknown():
    with pytest.raises(ValueError):
        build_llm_provider(Secrets(llm_provider="bogus"))

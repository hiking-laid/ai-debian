"""Device-flow auth tests using a fake httpx client (no real network, no real sleep)."""

from __future__ import annotations

import pytest

from toddler_dinner.providers.llm.copilot import CopilotLLMProvider
from toddler_dinner.providers.llm.github_auth import (
    DeviceCode,
    DeviceFlowError,
    device_login,
    load_oauth_token,
    poll_for_token,
    request_device_code,
    save_oauth_token,
)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeClient:
    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.posts: list[dict] = []

    def post(self, url, data=None, json=None, headers=None):
        self.posts.append({"url": url, "data": data, "json": json})
        return FakeResponse(self._responses.pop(0))


def _device_payload() -> dict:
    return {
        "device_code": "dev-123",
        "user_code": "ABCD-1234",
        "verification_uri": "https://github.com/login/device",
        "interval": 1,
        "expires_in": 60,
    }


def test_request_device_code_parses():
    client = FakeClient([_device_payload()])
    d = request_device_code(client=client)
    assert d.user_code == "ABCD-1234"
    assert d.verification_uri.endswith("/device")
    assert client.posts[0]["data"]["client_id"]


def test_poll_waits_then_returns_token():
    client = FakeClient([
        {"error": "authorization_pending"},
        {"error": "slow_down"},
        {"access_token": "gho_realtoken"},
    ])
    slept: list[float] = []
    device = DeviceCode("dev", "code", "uri", interval=1, expires_in=60)
    token = poll_for_token(device, client=client, sleep=slept.append)
    assert token == "gho_realtoken"
    assert len(slept) == 2  # pending + slow_down


def test_poll_raises_on_denied():
    client = FakeClient([{"error": "access_denied"}])
    device = DeviceCode("dev", "code", "uri", interval=1, expires_in=60)
    with pytest.raises(DeviceFlowError):
        poll_for_token(device, client=client, sleep=lambda _: None)


def test_device_login_end_to_end():
    client = FakeClient([_device_payload(), {"access_token": "gho_x"}])
    prompts: list[DeviceCode] = []
    token = device_login(on_prompt=prompts.append, client=client)
    assert token == "gho_x"
    assert prompts[0].user_code == "ABCD-1234"  # user was shown the code


def test_token_cache_round_trip(tmp_path):
    p = tmp_path / "oauth.json"
    assert load_oauth_token(p) is None
    save_oauth_token("gho_cached", p)
    assert load_oauth_token(p) == "gho_cached"
    assert (p.stat().st_mode & 0o777) == 0o600


def test_copilot_uses_cached_oauth_token(tmp_path):
    p = tmp_path / "oauth.json"
    save_oauth_token("gho_from_cache", p)
    # No explicit github/copilot token -> should load from cache and exchange it.
    exchange = FakeResponse({"token": "cop-xyz", "expires_at": 9999999999})
    chat = FakeResponse({"choices": [{"message": {"content": "hi"}}]})

    class ExchangeClient:
        def __init__(self):
            self.gets = []
            self.posts = []

        def get(self, url, headers=None):
            self.gets.append({"url": url, "headers": headers})
            return exchange

        def post(self, url, json=None, headers=None):
            self.posts.append({"url": url, "headers": headers})
            return chat

    client = ExchangeClient()
    prov = CopilotLLMProvider(model="gpt-4o", client=client, oauth_token_path=p)
    assert prov.complete("s", "u") == "hi"
    assert client.gets[0]["headers"]["Authorization"] == "token gho_from_cache"
    assert client.posts[0]["headers"]["Authorization"] == "Bearer cop-xyz"

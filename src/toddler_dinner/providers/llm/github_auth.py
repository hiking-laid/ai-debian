"""GitHub OAuth device-flow login for Copilot.

A Personal Access Token cannot obtain a Copilot token. The Copilot token exchange requires the
OAuth token an editor gets via GitHub's *device flow*:

  1. Request a device + user code from GitHub.
  2. User opens the verification URL and enters the user code in a browser.
  3. Poll until GitHub returns an OAuth access token.

That access token is then exchanged for a short-lived Copilot token (see copilot.py).

NOTE: Uses the well-known GitHub Copilot OAuth client id and undocumented Copilot endpoints.
Not officially supported; may break if GitHub changes it.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

# Well-known GitHub Copilot OAuth client id (used by editor integrations).
COPILOT_CLIENT_ID = "Iv1.b507a08c87ecfe98"
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

DEFAULT_TOKEN_PATH = Path.home() / ".toddler_dinner" / "copilot_oauth.json"

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "GitHubCopilotChat/0.22.0",
    "Editor-Version": "vscode/1.95.0",
}


@dataclass
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    interval: int
    expires_in: int


class DeviceFlowError(RuntimeError):
    pass


def request_device_code(
    client_id: str = COPILOT_CLIENT_ID, client: httpx.Client | None = None
) -> DeviceCode:
    c = client or httpx.Client(timeout=30)
    resp = c.post(DEVICE_CODE_URL, data={"client_id": client_id, "scope": "read:user"},
                  headers=_HEADERS)
    resp.raise_for_status()
    d = resp.json()
    return DeviceCode(
        device_code=d["device_code"],
        user_code=d["user_code"],
        verification_uri=d["verification_uri"],
        interval=int(d.get("interval", 5)),
        expires_in=int(d.get("expires_in", 900)),
    )


def poll_for_token(
    device: DeviceCode,
    client_id: str = COPILOT_CLIENT_ID,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Blocking poll until the user authorizes. Returns the OAuth access token."""
    c = client or httpx.Client(timeout=30)
    interval = device.interval
    deadline = time.time() + device.expires_in
    while time.time() < deadline:
        resp = c.post(
            ACCESS_TOKEN_URL,
            data={"client_id": client_id, "device_code": device.device_code,
                  "grant_type": DEVICE_GRANT},
            headers=_HEADERS,
        )
        resp.raise_for_status()
        d = resp.json()
        if d.get("access_token"):
            return d["access_token"]
        error = d.get("error")
        if error == "authorization_pending":
            sleep(interval)
        elif error == "slow_down":
            interval += 5
            sleep(interval)
        elif error in ("expired_token", "access_denied"):
            raise DeviceFlowError(f"device login failed: {error}")
        else:
            raise DeviceFlowError(f"unexpected device-flow response: {d}")
    raise DeviceFlowError("device login timed out")


def device_login(
    on_prompt: Callable[[DeviceCode], None],
    client_id: str = COPILOT_CLIENT_ID,
    client: httpx.Client | None = None,
) -> str:
    """Run the full device flow. `on_prompt` shows the code/URL to the user."""
    c = client or httpx.Client(timeout=30)
    device = request_device_code(client_id, client=c)
    on_prompt(device)
    return poll_for_token(device, client_id, client=c)


# --- token cache ------------------------------------------------------------

def save_oauth_token(token: str, path: Path = DEFAULT_TOKEN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"access_token": token}))
    os.chmod(path, 0o600)


def load_oauth_token(path: Path = DEFAULT_TOKEN_PATH) -> str | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text()).get("access_token")
    except (json.JSONDecodeError, OSError):
        return None

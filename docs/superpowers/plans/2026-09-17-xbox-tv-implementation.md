# Xbox TV Home Assistant Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a HACS custom integration `xbox_tv` that exposes an Xbox Series S|X as a Home Assistant Television media player (power + source switching) so Apple Home can use it as a TV accessory.

**Architecture:** Local SmartGlass UDP (port 5050) handles wake and on/off presence. Encrypted local sessions are out of v1; power off, current AUMID, installed titles, Dashboard, and app launch use Xbox Network remote-management REST (`https://xccs.xboxlive.com`) after Microsoft OAuth. A `DataUpdateCoordinator` merges both into one `media_player` with `device_class: tv`. HomeKit pairing is documented, not implemented in this integration.

**Tech Stack:** Python 3.13, Home Assistant custom component (config flow), pytest (pure unit tests, no HA core required for CI), asyncio UDP, aiohttp for Xbox REST, OpenXbox public OAuth client `388ea51c-0b25-4029-aae2-17df49d23905`.

## Global Constraints

- Domain is `xbox_tv` (must not collide with core `xbox`).
- `manifest.json` `iot_class` is `local_polling`.
- Media player `device_class` is TV; supported features v1 only: `TURN_ON`, `TURN_OFF`, `SELECT_SOURCE`.
- Unique id is the Xbox network device ID (live ID).
- SmartGlass poll timeout is 5 seconds; coordinator poll interval is 10 seconds; title catalog refresh is 15 minutes.
- Unreachable / no discovery reply maps to media player `off`, never `unavailable`.
- HomeKit accessory YAML is README/config-flow text only; do not speak HAP or write `configuration.yaml`.
- Do not log access tokens, refresh tokens, or client secrets.
- No volume, mute, remote keys, extra switches, sensors, MQTT, REST server, or in-integration HAP.
- Async only on the event loop; no blocking SmartGlass I/O.
- Tests live under `tests/` and must run with `pytest` without installing Home Assistant (keep HA-entity code thin; put behavior in pure functions).
- Default OAuth client id is `388ea51c-0b25-4029-aae2-17df49d23905` (OpenXbox / xbox-webapi public desktop app). Sign-in is a paste-the-redirect-URL flow using redirect `https://login.live.com/oauth20_desktop.srf` is wrong — use `http://localhost/auth/callback` (OpenXbox registered URI). User pastes the final redirect URL containing `code=`.
- Dashboard source name is exactly `Dashboard`. Dashboard AUMID is `Xbox.Dashboard_8wekyb3d8bbwe!Xbox.Dashboard.Application`.
- `source_list` max 100 entries for HomeKit.
- Work from repo root `/Users/stefanscanteie/Downloads/xbox-ha` on branch `feat/xbox-tv` (create it if missing). Do not implement on `main`.
- Follow TDD: failing test first, then minimal implementation. Commit after each task.

## File Structure

```
custom_components/xbox_tv/
  __init__.py
  manifest.json
  const.py
  config_flow.py
  coordinator.py
  media_player.py
  smartglass.py
  xbox_api.py
  strings.json
  translations/en.json
hacs.json
README.md
pyproject.toml
tests/conftest.py
tests/test_const.py
tests/test_smartglass_packets.py
tests/test_smartglass_client.py
tests/test_xbox_api.py
tests/test_coordinator.py
tests/test_media_player.py
tests/test_config_validation.py
```

---

### Task 1: Scaffold, constants, SmartGlass packets

**Files:**
- Create: `pyproject.toml`
- Create: `custom_components/xbox_tv/manifest.json`
- Create: `custom_components/xbox_tv/const.py`
- Create: `custom_components/xbox_tv/smartglass.py`
- Create: `custom_components/xbox_tv/__init__.py` (empty module docstring only in this task if needed for imports; do not register HA yet)
- Create: `tests/conftest.py`
- Create: `tests/test_const.py`
- Create: `tests/test_smartglass_packets.py`
- Create: `hacs.json`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `xbox_tv.const.DOMAIN = "xbox_tv"`
  - `xbox_tv.const.DEFAULT_NAME = "Xbox"`
  - `xbox_tv.const.CONF_LIVE_ID = "live_id"`
  - `xbox_tv.const.SMARTGLASS_PORT = 5050`
  - `xbox_tv.const.POLL_TIMEOUT = 5.0`
  - `xbox_tv.const.SCAN_INTERVAL = 10` (seconds)
  - `xbox_tv.const.TITLE_REFRESH_INTERVAL = 900` (seconds)
  - `xbox_tv.const.DASHBOARD_SOURCE = "Dashboard"`
  - `xbox_tv.const.DASHBOARD_AUMID = "Xbox.Dashboard_8wekyb3d8bbwe!Xbox.Dashboard.Application"`
  - `xbox_tv.const.OAUTH_CLIENT_ID = "388ea51c-0b25-4029-aae2-17df49d23905"`
  - `xbox_tv.const.OAUTH_REDIRECT_URI = "http://localhost/auth/callback"`
  - `xbox_tv.const.OAUTH_SCOPES = "XboxLive.signin XboxLive.offline_access"`
  - `xbox_tv.const.MAX_SOURCES = 100`
  - `xbox_tv.const.is_valid_host(host: str) -> bool`
  - `xbox_tv.const.is_valid_live_id(live_id: str) -> bool`
  - `xbox_tv.smartglass.encode_sg_string(value: str) -> bytes`
  - `xbox_tv.smartglass.decode_sg_string(data: bytes, offset: int = 0) -> tuple[str, int]`  # value, new_offset
  - `xbox_tv.smartglass.encode_simple_header(packet_type: int, unprotected_len: int, version: int) -> bytes`
  - `xbox_tv.smartglass.encode_power_on(live_id: str) -> bytes`
  - `xbox_tv.smartglass.encode_discovery_request() -> bytes`
  - `xbox_tv.smartglass.is_discovery_response(data: bytes) -> bool`

- [ ] **Step 1: Write failing tests**

`tests/conftest.py`:

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
```

`tests/test_const.py`:

```python
from xbox_tv.const import is_valid_host, is_valid_live_id


def test_valid_host_accepts_ipv4_and_hostname() -> None:
    assert is_valid_host("192.168.1.50") is True
    assert is_valid_host("xbox.local") is True


def test_valid_host_rejects_empty() -> None:
    assert is_valid_host("") is False
    assert is_valid_host("   ") is False


def test_valid_live_id_accepts_hex() -> None:
    assert is_valid_live_id("FD00112233445566") is True
    assert is_valid_live_id("fd00112233445566") is True


def test_valid_live_id_rejects_short_or_non_alnum() -> None:
    assert is_valid_live_id("FD00") is False
    assert is_valid_live_id("FD00-1122-3344") is False
    assert is_valid_live_id("") is False
```

`tests/test_smartglass_packets.py`:

```python
from xbox_tv.smartglass import (
    decode_sg_string,
    encode_discovery_request,
    encode_power_on,
    encode_sg_string,
    is_discovery_response,
)

LIVE_ID = "FD00112233445566"


def test_sg_string_roundtrip() -> None:
    encoded = encode_sg_string(LIVE_ID)
    value, offset = decode_sg_string(encoded, 0)
    assert value == LIVE_ID
    assert offset == len(encoded)
    assert encoded == bytes([0x00, 0x10]) + LIVE_ID.encode("ascii") + b"\x00"


def test_power_on_packet_matches_openxbox_simple_message() -> None:
    packet = encode_power_on(LIVE_ID)
    assert packet[:2] == bytes([0xDD, 0x02])
    payload = encode_sg_string(LIVE_ID)
    assert packet[2:4] == len(payload).to_bytes(2, "big")
    assert packet[4:6] == bytes([0x00, 0x02])
    assert packet[6:] == payload


def test_discovery_request_is_plaintext_dd00_version_0() -> None:
    packet = encode_discovery_request()
    assert packet[:2] == bytes([0xDD, 0x00])
    assert packet[4:6] == bytes([0x00, 0x00])
    assert len(packet) == 6 + 10
    assert is_discovery_response(packet) is False


def test_discovery_response_detects_dd01() -> None:
    header = bytes([0xDD, 0x01, 0x00, 0x04, 0x00, 0x00]) + b"\x00\x00\x00\x00"
    assert is_discovery_response(header) is True
    assert is_discovery_response(b"\x00\x00") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_const.py tests/test_smartglass_packets.py -v`

Expected: FAIL with `ModuleNotFoundError: xbox_tv` or import error.

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`:

```toml
[project]
name = "xbox-ha"
version = "0.1.0"
description = "Home Assistant Xbox TV custom integration"
requires-python = ">=3.13"
readme = "README.md"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["custom_components"]
```

`hacs.json`:

```json
{
  "name": "Xbox TV",
  "content_in_root": false,
  "filename": "xbox_tv",
  "homeassistant": "2025.1.0",
  "render_readme": true
}
```

`custom_components/xbox_tv/manifest.json`:

```json
{
  "domain": "xbox_tv",
  "name": "Xbox TV",
  "codeowners": [],
  "config_flow": true,
  "documentation": "https://github.com/stefanscanteie/xbox-ha",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/stefanscanteie/xbox-ha/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

`custom_components/xbox_tv/const.py`:

```python
"""Constants for the Xbox TV integration."""

from __future__ import annotations

import re

DOMAIN = "xbox_tv"
DEFAULT_NAME = "Xbox"
CONF_LIVE_ID = "live_id"
CONF_TOKENS = "tokens"
CONF_CLIENT_ID = "client_id"

SMARTGLASS_PORT = 5050
POLL_TIMEOUT = 5.0
SCAN_INTERVAL = 10
TITLE_REFRESH_INTERVAL = 900
TURN_ON_WAIT = 30
LAUNCH_WAIT = 30

DASHBOARD_SOURCE = "Dashboard"
DASHBOARD_AUMID = "Xbox.Dashboard_8wekyb3d8bbwe!Xbox.Dashboard.Application"
MAX_SOURCES = 100

OAUTH_CLIENT_ID = "388ea51c-0b25-4029-aae2-17df49d23905"
OAUTH_REDIRECT_URI = "http://localhost/auth/callback"
OAUTH_SCOPES = "XboxLive.signin XboxLive.offline_access"
OAUTH_AUTHORIZE_URL = "https://login.live.com/oauth20_authorize.srf"
OAUTH_TOKEN_URL = "https://login.live.com/oauth20_token.srf"

LIVE_ID_RE = re.compile(r"^[A-Fa-f0-9]{8,32}$")


def is_valid_host(host: str) -> bool:
    return bool(host and host.strip() and not host.strip().isspace())


def is_valid_live_id(live_id: str) -> bool:
    return bool(LIVE_ID_RE.fullmatch(live_id.strip()))
```

Fix `is_valid_host`: empty after strip is False. `host.strip()` truthy is enough:

```python
def is_valid_host(host: str) -> bool:
    return bool(host.strip())
```

`custom_components/xbox_tv/smartglass.py` packet functions (client class comes in Task 2; include the functions now):

```python
"""Xbox SmartGlass plaintext packets and LAN client."""

from __future__ import annotations

import struct

PACKET_DISCOVERY_REQUEST = 0xDD00
PACKET_DISCOVERY_RESPONSE = 0xDD01
PACKET_POWER_ON = 0xDD02
CLIENT_TYPE_ANDROID = 0x0008


def encode_sg_string(value: str) -> bytes:
    payload = value.encode("ascii")
    return struct.pack(">H", len(payload)) + payload + b"\x00"


def decode_sg_string(data: bytes, offset: int = 0) -> tuple[str, int]:
    length = struct.unpack_from(">H", data, offset)[0]
    start = offset + 2
    end = start + length
    value = data[start:end].decode("ascii")
    return value, end + 1


def encode_simple_header(packet_type: int, unprotected_len: int, version: int) -> bytes:
    return struct.pack(">HHH", packet_type, unprotected_len, version)


def encode_power_on(live_id: str) -> bytes:
    payload = encode_sg_string(live_id.upper())
    return encode_simple_header(PACKET_POWER_ON, len(payload), 2) + payload


def encode_discovery_request() -> bytes:
    payload = struct.pack(">IHHH", 0, CLIENT_TYPE_ANDROID, 0, 2)
    return encode_simple_header(PACKET_DISCOVERY_REQUEST, len(payload), 0) + payload


def is_discovery_response(data: bytes) -> bool:
    if len(data) < 2:
        return False
    return struct.unpack_from(">H", data, 0)[0] == PACKET_DISCOVERY_RESPONSE
```

`custom_components/xbox_tv/__init__.py`:

```python
"""Xbox TV Home Assistant custom integration."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_const.py tests/test_smartglass_packets.py -v`

Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml hacs.json custom_components/xbox_tv tests
git commit -m "$(cat <<'EOF'
Add Xbox TV scaffold and SmartGlass plaintext packets.

EOF
)"
```

---

### Task 2: Async SmartGlass LAN client

**Files:**
- Modify: `custom_components/xbox_tv/smartglass.py`
- Create: `tests/test_smartglass_client.py`

**Interfaces:**
- Consumes: packet helpers and `SMARTGLASS_PORT`, `POLL_TIMEOUT` from Task 1
- Produces:
  - `class SmartGlassClient:`
    - `__init__(self, host: str, live_id: str, port: int = SMARTGLASS_PORT, timeout: float = POLL_TIMEOUT) -> None`
    - `async def async_get_powered_on(self) -> bool`
    - `async def async_power_on(self) -> None`
  - `async_get_powered_on` sends a discovery request to `(host, port)` and returns True if a discovery response arrives within `timeout`, else False.
  - `async_power_on` sends the power-on packet to the console IP, `255.255.255.255`, and `239.255.255.250` (ignore send errors on broadcast/multicast). Send each destination twice.

Inject a transport for tests: optional `send_and_recv` callable. Default implementation uses asyncio datagram endpoint.

```python
class SmartGlassClient:
    def __init__(
        self,
        host: str,
        live_id: str,
        port: int = SMARTGLASS_PORT,
        timeout: float = POLL_TIMEOUT,
        *,
        udp: UdpTransport | None = None,
    ) -> None: ...
```

Define a protocol in `smartglass.py`:

```python
class UdpTransport(Protocol):
    async def send(self, data: bytes, host: str, port: int) -> None: ...
    async def send_recv(
        self, data: bytes, host: str, port: int, timeout: float
    ) -> bytes | None: ...
```

Default `AsyncioUdpTransport` uses `loop.create_datagram_endpoint`.

- [ ] **Step 1: Write failing tests**

`tests/test_smartglass_client.py`:

```python
import pytest

from xbox_tv.smartglass import (
    SmartGlassClient,
    encode_discovery_request,
    encode_power_on,
    is_discovery_response,
)


class FakeUdp:
    def __init__(self, response: bytes | None = None) -> None:
        self.sent: list[tuple[bytes, str, int]] = []
        self.response = response

    async def send(self, data: bytes, host: str, port: int) -> None:
        self.sent.append((data, host, port))

    async def send_recv(
        self, data: bytes, host: str, port: int, timeout: float
    ) -> bytes | None:
        self.sent.append((data, host, port))
        return self.response


@pytest.mark.asyncio
async def test_get_powered_on_true_on_discovery_response() -> None:
    reply = bytes([0xDD, 0x01, 0x00, 0x00, 0x00, 0x00])
    udp = FakeUdp(reply)
    client = SmartGlassClient("192.168.1.50", "FD00112233445566", udp=udp)
    assert await client.async_get_powered_on() is True
    assert udp.sent[0][0] == encode_discovery_request()
    assert udp.sent[0][1:] == ("192.168.1.50", 5050)


@pytest.mark.asyncio
async def test_get_powered_on_false_on_timeout() -> None:
    client = SmartGlassClient("192.168.1.50", "FD00112233445566", udp=FakeUdp(None))
    assert await client.async_get_powered_on() is False


@pytest.mark.asyncio
async def test_power_on_sends_to_host_broadcast_and_multicast() -> None:
    udp = FakeUdp()
    live_id = "FD00112233445566"
    client = SmartGlassClient("192.168.1.50", live_id, udp=udp)
    await client.async_power_on()
    packet = encode_power_on(live_id)
    hosts = [dest for _data, dest, _port in udp.sent]
    assert hosts.count("192.168.1.50") == 2
    assert hosts.count("255.255.255.255") == 2
    assert hosts.count("239.255.255.250") == 2
    assert all(data == packet for data, _h, _p in udp.sent)
```

Add `pytest-asyncio` to `pyproject.toml` optional/dev or document `pip install pytest pytest-asyncio`. Add:

```toml
[project.optional-dependencies]
test = ["pytest>=8", "pytest-asyncio>=0.24"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["custom_components"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pip install pytest pytest-asyncio -q && python3 -m pytest tests/test_smartglass_client.py -v`

Expected: FAIL because `SmartGlassClient` is missing.

- [ ] **Step 3: Write minimal implementation**

Append to `smartglass.py` the `UdpTransport` protocol, `AsyncioUdpTransport`, and `SmartGlassClient` as specified. `send_recv` must not block the event loop: use `asyncio.wait_for` around a Future set by `datagram_received`. If `send` to broadcast fails, swallow `OSError`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_smartglass_client.py tests/test_smartglass_packets.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/xbox_tv/smartglass.py tests/test_smartglass_client.py pyproject.toml
git commit -m "$(cat <<'EOF'
Add async SmartGlass client for wake and presence.

EOF
)"
```

---

### Task 3: Title catalog, source list, OAuth URL helpers

**Files:**
- Create: `custom_components/xbox_tv/xbox_api.py`
- Create: `tests/test_xbox_api.py`
- Create: `tests/test_config_validation.py`
- Modify: `custom_components/xbox_tv/const.py` only if adding `extract_oauth_code` — put `extract_oauth_code` and `build_authorize_url` in `xbox_api.py` instead.

**Interfaces:**
- Consumes: constants from Task 1
- Produces:
  - `@dataclass(frozen=True) class Title: name: str; launch_id: str; aumid: str | None = None`
  - `parse_installed_apps(payload: dict) -> list[Title]`
  - `parse_active_aumid(status_payload: dict) -> str | None`
  - `build_source_list(titles: list[Title], current_aumid: str | None, current_name: str | None) -> list[str]`
  - `launch_id_for_source(source: str, titles: list[Title]) -> str | None`  # None means unknown; Dashboard is not a launch id
  - `is_dashboard_source(source: str) -> bool`
  - `friendly_source(titles: list[Title], aumid: str | None) -> str`  # Dashboard if missing/dashboard AUMID
  - `build_authorize_url(client_id: str, redirect_uri: str) -> str`
  - `extract_oauth_code(redirect_url: str) -> str | None`

`parse_installed_apps` reads `payload["result"]` list. Each item: `name`, `oneStoreProductId` or `titleId` as launch_id (prefer oneStoreProductId if non-empty), `aum` or `aumid` for AUMID. Skip items with no name or no launch_id.

`parse_active_aumid`: prefer `payload["status"]["activeTitles"][0]["aum"]` then `[0]["aumid"]`; also accept top-level `activeTitles`.

`build_source_list`:
1. Start with `["Dashboard"]`.
2. Sort remaining titles by name casefold, unique by launch_id.
3. If current title (match aumid) is not in the list by name, append `current_name` or aumid.
4. If len > 100: keep Dashboard, keep current source name if not Dashboard, then fill remaining slots from the alphabetical titles. Log via `logging.getLogger(__name__).warning`.

- [ ] **Step 1: Write failing tests**

Include tests:

- Netflix + Halo → `["Dashboard", "Halo Infinite", "Netflix"]`
- Duplicate launch ids collapsed
- Current AUMID not in catalog appends current name
- 120 titles truncates to 100 including Dashboard and current
- Empty catalog → `["Dashboard"]`
- `launch_id_for_source("Netflix", titles) == "9WZDNCRFJ3TJ"`
- `launch_id_for_source("Dashboard", titles) is None` and `is_dashboard_source("Dashboard")`
- `friendly_source` dashboard AUMID → `Dashboard`
- `parse_active_aumid` fixture
- `extract_oauth_code("http://localhost/auth/callback?code=ABC&lc=1033") == "ABC"`
- `extract_oauth_code("http://localhost/auth/callback?error=access_denied") is None`

Use this installed-apps fixture:

```python
APPS = {
    "result": [
        {
            "name": "Netflix",
            "oneStoreProductId": "9WZDNCRFJ3TJ",
            "aum": "Netflix.App",
        },
        {
            "name": "Halo Infinite",
            "oneStoreProductId": "9PP5G15W52VT",
            "titleId": "123",
            "aum": "Halo.Infinite",
        },
        {"name": "NoId"},
    ]
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_xbox_api.py tests/test_config_validation.py -v`

Expected: FAIL import of `xbox_api`.

- [ ] **Step 3: Write minimal implementation** in `xbox_api.py` (HTTP client methods come in Task 4; parsers + URL helpers only now).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_xbox_api.py tests/test_config_validation.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
Add Xbox title catalog parsing and source list rules.

EOF
)"
```

---

### Task 4: Xbox Network REST client

**Files:**
- Modify: `custom_components/xbox_tv/xbox_api.py`
- Modify: `tests/test_xbox_api.py`

**Interfaces:**
- Consumes: parsers from Task 3
- Produces:
  - `class XboxWebApiClient:`
    - `__init__(self, session: aiohttp.ClientSession, tokens: dict, live_id: str, client_id: str = OAUTH_CLIENT_ID) -> None`
    - `async def async_ensure_token(self) -> str`  # returns XBL3.0 authorization header value; refresh MSA token if expired
    - `async def async_installed_titles(self) -> list[Title]`
    - `async def async_active_aumid(self) -> str | None`
    - `async def async_turn_off(self) -> None`
    - `async def async_go_home(self) -> None`
    - `async def async_launch(self, launch_id: str) -> None`
    - `tokens` property returning the current token dict (for config entry updates)

Token dict shape stored in config entry:

```python
{
  "access_token": str,
  "refresh_token": str,
  "expires_at": float,  # unix ts
  "userhash": str,
  "xsts_token": str,
  "xsts_expires_at": float,
}
```

HTTP (all with `Authorization: XBL3.0 x={userhash};{xsts_token}` and headers `skillplatform: RemoteManagement`, `x-xbl-contract-version: 4`, `Content-Type: application/json`):

- GET `https://xccs.xboxlive.com/lists/installedApps?deviceId={live_id}`
- GET `https://xccs.xboxlive.com/consoles/{live_id}` for status (if 404, GET `https://xccs.xboxlive.com/consoles/{live_id}/status`)
- POST `https://xccs.xboxlive.com/commands` body:

```python
{
  "destination": "Xbox",
  "type": command_type,
  "command": command,
  "sessionId": str(uuid4()),
  "sourceId": "com.microsoft.smartglass",
  "parameters": parameters or [],
  "linkedDeviceId": live_id,
}
```

- Power off: `type="Power", command="TurnOff"`
- Go home: `type="Shell", command="GoHome"`
- Launch: `type="Shell", command="ActivateApplicationWithAumid"` **No** — use `Launch` / `Activate` with parameter `OneStoreProductId` as homebridge/xbox-webapi:

xbox-webapi `launch_app` uses command `Activate` with params `[{"oneStoreProductId": launch_id}]` and type `Shell`. Use:

```python
type="Shell", command="Activate", parameters=[{"oneStoreProductId": launch_id}]
```

MSA refresh: POST `OAUTH_TOKEN_URL` with `client_id`, `refresh_token`, `grant_type=refresh_token`, `scope`. Then XSTS:

1. POST `https://user.auth.xboxlive.com/user/authenticate` with RPS ticket `d={access_token}`
2. POST `https://xsts.auth.xboxlive.com/xsts/authorize` relyingParty `http://xboxlive.com`

Implement `async def exchange_code_for_tokens(session, code, client_id) -> dict` as a module function for config flow.

Do not log token bodies.

Inject session; tests use a fake aiohttp-like object:

```python
class FakeResponse:
    def __init__(self, status, json_data):
        self.status = status
        self._json = json_data
    async def json(self):
        return self._json
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return None
    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(self.status)

class FakeSession:
    def __init__(self, mapping):
        self.mapping = mapping  # (method, url_prefix) -> FakeResponse
        self.calls = []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        for (m, prefix), resp in self.mapping.items():
            if method == m and url.startswith(prefix):
                return resp
        return FakeResponse(404, {})
    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)
    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)
```

If real aiohttp context manager is expected (`async with session.get`), implement FakeSession.get to return FakeResponse that supports async with.

Skip live XSTS in `async_installed_titles` tests by constructing client with tokens that are not expired (`expires_at` and `xsts_expires_at` = now+3600) so `async_ensure_token` does not refresh.

- [ ] **Step 1: Write failing tests** for installed titles, active aumid, turn_off POST body, launch POST body, go_home POST body.
- [ ] **Step 2: Run to verify fail**
- [ ] **Step 3: Implement `XboxWebApiClient` + `exchange_code_for_tokens`**
- [ ] **Step 4: Run tests pass**
- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
Add Xbox Network client for titles, launch, and power off.

EOF
)"
```

---

### Task 5: Coordinator and media player behavior

**Files:**
- Create: `custom_components/xbox_tv/coordinator.py`
- Create: `custom_components/xbox_tv/media_player.py`
- Create: `tests/test_coordinator.py`
- Create: `tests/test_media_player.py`

**Interfaces:**
- Consumes: `SmartGlassClient`, `XboxWebApiClient`, title helpers
- Produces:
  - `@dataclass class XboxTvState: powered_on: bool; aumid: str | None; titles: list[Title]; source_list: list[str]; source: str; microsoft_connected: bool`
  - `class XboxTvCoordinator:` **not** a HA DataUpdateCoordinator subclass in the testable core. Put update logic in `async def async_fetch_state(smartglass, webapi, titles_cache, microsoft_connected) -> XboxTvState` and a thin HA wrapper class `XboxTvCoordinator(DataUpdateCoordinator[XboxTvState])` in the same file that calls it.

  To keep tests HA-free, structure:

```python
# coordinator.py
async def async_fetch_state(
    smartglass: SmartGlassClient,
    webapi: XboxWebApiClient | None,
    titles_cache: list[Title],
) -> XboxTvState:
    powered_on = await smartglass.async_get_powered_on()
    aumid = None
    titles = titles_cache
    microsoft_connected = webapi is not None
    if webapi is not None:
        try:
            aumid = await webapi.async_active_aumid()
        except Exception:
            aumid = None
        try:
            titles = await webapi.async_installed_titles()
        except Exception:
            titles = titles_cache
    source_list = build_source_list(titles, aumid, None)
    source = friendly_source(titles, aumid) if powered_on else DASHBOARD_SOURCE
    if powered_on and aumid:
        source = friendly_source(titles, aumid)
    elif powered_on:
        source = DASHBOARD_SOURCE
    else:
        source = DASHBOARD_SOURCE
    return XboxTvState(...)
```

When off, `source` can still be Dashboard. Fine.

Catalog refresh: the HA coordinator wrapper refreshes titles only if `now - last_title_refresh >= 900` or titles_cache empty; `async_fetch_state` always asks webapi in unit tests; the wrapper in HA throttles. Implement throttle in `XboxTvCoordinator._async_update_data` using `time.monotonic()`.

  - Pure media actions in `media_player.py`:

```python
@dataclass(frozen=True)
class SourceAction:
    kind: str  # "dashboard" | "launch" | "signin" | "unknown"
    launch_id: str | None = None

def resolve_source_action(
    source: str,
    titles: list[Title],
    microsoft_connected: bool,
) -> SourceAction: ...
```

- Dashboard → `SourceAction("dashboard")`
- Known title + microsoft → `SourceAction("launch", launch_id)`
- Known title without microsoft impossible if titles empty; unknown name without microsoft → `signin` if not dashboard
- Unknown name + microsoft → `unknown`
- Non-dashboard + not microsoft → `signin`

Media player entity (HA):

```python
class XboxTvMediaPlayer(CoordinatorEntity[XboxTvCoordinator], MediaPlayerEntity):
    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )
    _attr_has_entity_name = True
    _attr_name = None
```

State: `STATE_ON` if `coordinator.data.powered_on` else `STATE_OFF`.

`async_turn_on`: `await smartglass.async_power_on()` then `hass.async_create_task` a waiter that polls `async_request_refresh` every 2s up to 30s. Return immediately.

`async_turn_off`: if webapi: `await webapi.async_turn_off()` else log warning. Then request refresh.

`async_select_source`: dispatch `resolve_source_action`; dashboard → `webapi.async_go_home`; launch → `webapi.async_launch`; signin → create HA issue/repair `xbox_tv_microsoft_sign_in` (if `homeassistant.helpers.issue_registry` import fails in tests, the pure function still returns signin). unknown → log warning.

Because importing `homeassistant` will fail in pytest, **split**:

- `media_player.py` may import HA.
- Keep `resolve_source_action` in `xbox_api.py` (already have launch_id helpers) so `tests/test_media_player.py` tests that function without HA.

Move `resolve_source_action` to `xbox_api.py`. `media_player.py` is HA glue only; add a test that imports `resolve_source_action` from xbox_api.

Add `tests/test_media_player.py` testing `resolve_source_action` only.

HA wrapper classes: implement them; no pytest on the HA subclass in v1 (manual test). Coordinator `async_fetch_state` is unit-tested.

- [ ] **Step 1: Write failing tests** for `async_fetch_state` (on/off, webapi down keeps cache, unreachable is off) and `resolve_source_action`.
- [ ] **Step 2: Run fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run pass**
- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
Add coordinator state merge and TV source actions.

EOF
)"
```

---

### Task 6: Config flow, integration setup, strings

**Files:**
- Create: `custom_components/xbox_tv/config_flow.py`
- Modify: `custom_components/xbox_tv/__init__.py`
- Create: `custom_components/xbox_tv/strings.json`
- Create: `custom_components/xbox_tv/translations/en.json`
- Modify: `custom_components/xbox_tv/coordinator.py` HA subclass if not finished
- Modify: `custom_components/xbox_tv/media_player.py` HA entity if not finished
- Create: `tests/test_config_validation.py` additions for authorize URL if missing

**Interfaces:**
- Consumes: validators, `exchange_code_for_tokens`, `build_authorize_url`, `extract_oauth_code`
- Produces: config flow class `XboxTvConfigFlow` domain `xbox_tv`

Config entry data:

```python
{
  "name": str,
  "host": str,
  "live_id": str,  # CONF_LIVE_ID
  "client_id": str,  # default OAUTH_CLIENT_ID
  "tokens": dict | omitted
}
```

Steps:
1. `async_step_user`: form name (default Xbox), host, live_id. Abort if live_id already configured (`unique_id = live_id.upper()`). On success go to `async_step_auth_choice`.
2. `async_step_auth_choice`: menu `sign_in` / `skip`. Skip → `async_create_entry`. Sign in → `async_step_oauth`.
3. `async_step_oauth`: description with authorize URL; field `redirect_url`. Parse code, exchange tokens, create entry. On bad URL, form error `invalid_code`.

Reconfigure: `async_step_reconfigure` same console fields; `async_step_reconfigure_auth` optional new tokens.

`__init__.py`:

```python
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_LIVE_ID, CONF_TOKENS, DOMAIN
from .coordinator import XboxTvCoordinator
from .media_player import async_setup_entry as async_setup_media_player  # or PLATFORMS

PLATFORMS = [Platform.MEDIA_PLAYER]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = XboxTvCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
```

`XboxTvCoordinator` constructor builds `SmartGlassClient` and optional `XboxWebApiClient` from entry data + `async_get_clientsession(hass)`.

Device info on the media player: identifiers `{(DOMAIN, live_id)}`, manufacturer Microsoft, model `Xbox Series`, name from config.

Config flow success description in strings: tell the user to add a **separate** HomeKit accessory in accessory mode including only this media player, and not to add it to the existing bridge.

`strings.json` / `translations/en.json` must include flow form labels and that HomeKit paragraph (`finish` / `abort` / `create_entry` description).

Repair: in `async_select_source` when action is signin, `ir.async_create_issue(hass, DOMAIN, "microsoft_sign_in", is_fixable=True, severity=WARNING, translation_key="microsoft_sign_in")`.

Because pytest cannot import HA, do not add HA config flow tests. Extra unit tests: `is_valid_host` / `is_valid_live_id` already exist; add `build_authorize_url` contains client_id and redirect_uri.

- [ ] **Step 1: Write failing test** if `build_authorize_url` not yet tested; otherwise skip to implementation of HA files (HA files are the deliverable; validators already tested). Add a test that `MAX_SOURCES == 100` and domain constant — already in task 1.

For this task TDD: add `tests/test_config_validation.py` test `test_authorize_url_includes_client_and_redirect` if missing.

- [ ] **Step 2: Run fail if new test**
- [ ] **Step 3: Implement HA glue files completely** (config_flow, __init__, coordinator HA class, media_player entity, strings, translations)
- [ ] **Step 4: Run full pytest** `python3 -m pytest tests -v` Expected: PASS all existing tests. HA modules are not imported by tests.
- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
Add config flow and Home Assistant TV media player.

EOF
)"
```

---

### Task 7: README and HomeKit setup docs

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: entity_id slug example `media_player.living_room_xbox`
- Produces: install + console prerequisites + HomeKit accessory YAML + non-goals

README sections (exact YAML):

```markdown
# Xbox TV

Home Assistant custom integration that exposes an Xbox Series S or Series X as a Television media player for Apple Home automations.

## Console settings

- Instant-on: Profile & system → Settings → General → Power mode & startup
- Allow connections from any device: Settings → Devices & connections → Remote features → Xbox app preferences

You need the **Xbox network device ID** (Settings → System → Console info), not the serial number.

## Install

HACS → Custom repositories → this GitHub repo → Integration category.

Or copy `custom_components/xbox_tv` into your Home Assistant `custom_components` folder and restart.

## Apple Home

Home Assistant already using a HomeKit **Bridge** must **not** include this media player on that bridge. Apple will not show a Television on a mixed bridge.

Add a second HomeKit entry in accessory mode with only the Xbox entity:

```yaml
homekit:
  - name: Xbox TV
    mode: accessory
    filter:
      include_entities:
        - media_player.living_room_xbox
```

Pair that accessory in Apple Home. Leave the existing bridge pairing alone.

If the Xbox was previously exposed as switches, remove it from HomeKit and re-add; HomeKit does not change accessory type in place. Television accessories need iOS 12.2 or later.

## Microsoft sign-in

Sign-in is required to list and launch apps/games and to power off. Power on and on/off presence use the local network. After opening the login URL, paste the full redirected `http://localhost/auth/callback?code=...` URL back into the form.

Default Microsoft client id is OpenXbox `388ea51c-0b25-4029-aae2-17df49d23905`.
```

Also mention v1 does not include volume or Apple Remote keys.

- [ ] **Step 1:** README is documentation; no unit test. Create the file with the content above plus a short “Entities” section describing the TV media player.
- [ ] **Step 2:** N/A
- [ ] **Step 3:** N/A
- [ ] **Step 4:** Confirm file exists and YAML matches spec.
- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
Document Xbox TV setup and HomeKit accessory pairing.

EOF
)"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
| --- | --- |
| Custom integration `xbox_tv`, HACS | 1, 7 |
| Local SmartGlass power on + presence 5s / 10s poll | 2, 5 |
| Unreachable = off | 5 |
| Microsoft OAuth, titles, launch, Dashboard | 3, 4, 6 |
| Skip OAuth degraded mode + repair | 5, 6 |
| TV media_player features | 5, 6 |
| source_list rules + 100 cap | 3 |
| HomeKit accessory docs, not HAP | 6, 7 |
| No volume/MQTT/HAP | all non-goals |
| Power off when local encrypted session not in v1 | Task 4 web API `TurnOff` (documented in README) |
| Tokens not logged | 4, 6 |
| Tests without console | 1–5 |

Placeholder scan: no TBD. Token HTTP 404 fallback for console status is specified. Launch command body specified.

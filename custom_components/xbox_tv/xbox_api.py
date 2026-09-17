"""Xbox title catalog parsing, OAuth helpers, and Network REST client."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import uuid4

from .const import (
    DASHBOARD_AUMID,
    DASHBOARD_SOURCE,
    MAX_SOURCES,
    OAUTH_AUTHORIZE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPES,
    OAUTH_TOKEN_URL,
)

XBOX_USER_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
XBOX_XSTS_AUTH_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
XBOX_COMMANDS_URL = "https://xccs.xboxlive.com/commands"
XSTS_LIFETIME = 23 * 3600

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Title:
    name: str
    launch_id: str
    aumid: str | None = None


@dataclass(frozen=True)
class SourceAction:
    kind: str  # "dashboard" | "launch" | "signin" | "unknown"
    launch_id: str | None = None


def parse_installed_apps(payload: dict) -> list[Title]:
    titles: list[Title] = []
    for item in payload.get("result", []):
        name = item.get("name")
        if not name:
            continue
        launch_id = item.get("oneStoreProductId") or item.get("titleId")
        if not launch_id:
            continue
        aumid = item.get("aum") or item.get("aumid")
        titles.append(Title(name=name, launch_id=launch_id, aumid=aumid))
    return titles


def parse_active_aumid(status_payload: dict) -> str | None:
    active_titles = status_payload.get("status", {}).get("activeTitles")
    if not active_titles:
        active_titles = status_payload.get("activeTitles")
    if not active_titles:
        return None
    first = active_titles[0]
    return first.get("aum") or first.get("aumid")


def is_dashboard_source(source: str) -> bool:
    return source == DASHBOARD_SOURCE


def launch_id_for_source(source: str, titles: list[Title]) -> str | None:
    if is_dashboard_source(source):
        return None
    for title in titles:
        if title.name == source:
            return title.launch_id
    return None


def resolve_source_action(
    source: str,
    titles: list[Title],
    microsoft_connected: bool,
) -> SourceAction:
    if is_dashboard_source(source):
        return SourceAction("dashboard")

    launch_id = launch_id_for_source(source, titles)
    if launch_id is not None:
        if microsoft_connected:
            return SourceAction("launch", launch_id)
        return SourceAction("signin")

    if microsoft_connected:
        return SourceAction("unknown")
    return SourceAction("signin")


def friendly_source(titles: list[Title], aumid: str | None) -> str:
    if not aumid or aumid == DASHBOARD_AUMID:
        return DASHBOARD_SOURCE
    for title in titles:
        if title.aumid == aumid:
            return title.name
    return aumid


def build_source_list(
    titles: list[Title],
    current_aumid: str | None,
    current_name: str | None,
) -> list[str]:
    seen_launch_ids: set[str] = set()
    unique_titles: list[Title] = []
    for title in sorted(titles, key=lambda item: item.name.casefold()):
        if title.launch_id in seen_launch_ids:
            continue
        seen_launch_ids.add(title.launch_id)
        unique_titles.append(title)

    sources = [DASHBOARD_SOURCE]
    sources.extend(title.name for title in unique_titles)

    current_friendly: str | None = None
    if current_aumid:
        for title in unique_titles:
            if title.aumid == current_aumid:
                current_friendly = title.name
                break
        if current_friendly is None:
            resolved = friendly_source(unique_titles, current_aumid)
            if resolved == current_aumid and current_name:
                current_friendly = current_name
            else:
                current_friendly = resolved
    elif current_name:
        current_friendly = current_name

    if current_friendly and current_friendly not in sources:
        sources.append(current_friendly)

    if len(sources) <= MAX_SOURCES:
        return sources

    _LOGGER.warning(
        "Source list truncated from %d to %d entries", len(sources), MAX_SOURCES
    )

    truncated = [DASHBOARD_SOURCE]
    if current_friendly and not is_dashboard_source(current_friendly):
        truncated.append(current_friendly)

    for title in unique_titles:
        if len(truncated) >= MAX_SOURCES:
            break
        if title.name not in truncated:
            truncated.append(title.name)

    return truncated


def build_authorize_url(client_id: str, redirect_uri: str) -> str:
    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": OAUTH_SCOPES,
        }
    )
    return f"{OAUTH_AUTHORIZE_URL}?{params}"


def extract_oauth_code(redirect_url: str) -> str | None:
    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)
    if "error" in params:
        return None
    codes = params.get("code")
    if codes:
        return codes[0]
    return None


def _api_headers(auth: str) -> dict[str, str]:
    return {
        "Authorization": auth,
        "skillplatform": "RemoteManagement",
        "x-xbl-contract-version": "4",
        "Content-Type": "application/json",
    }


async def _fetch_xsts_tokens(session: Any, access_token: str) -> tuple[str, str]:
    user_payload = {
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": f"d={access_token}",
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT",
    }
    async with session.post(XBOX_USER_AUTH_URL, json=user_payload) as resp:
        resp.raise_for_status()
        user_data = await resp.json()

    user_token = user_data["Token"]
    userhash = user_data["DisplayClaims"]["xui"][0]["uhs"]

    xsts_payload = {
        "Properties": {
            "SandboxId": "RETAIL",
            "UserTokens": [user_token],
        },
        "RelyingParty": "http://xboxlive.com",
        "TokenType": "JWT",
    }
    async with session.post(XBOX_XSTS_AUTH_URL, json=xsts_payload) as resp:
        resp.raise_for_status()
        xsts_data = await resp.json()

    return userhash, xsts_data["Token"]


async def exchange_code_for_tokens(
    session: Any, code: str, client_id: str = OAUTH_CLIENT_ID
) -> dict[str, Any]:
    token_payload = {
        "client_id": client_id,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": OAUTH_REDIRECT_URI,
        "scope": OAUTH_SCOPES,
    }
    async with session.post(OAUTH_TOKEN_URL, data=token_payload) as resp:
        resp.raise_for_status()
        token_data = await resp.json()

    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]
    expires_at = time.time() + float(token_data.get("expires_in", 3600))
    userhash, xsts_token = await _fetch_xsts_tokens(session, access_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "userhash": userhash,
        "xsts_token": xsts_token,
        "xsts_expires_at": time.time() + XSTS_LIFETIME,
    }


class XboxWebApiClient:
    """Xbox Network REST client for titles, status, and remote commands."""

    def __init__(
        self,
        session: Any,
        tokens: dict[str, Any],
        live_id: str,
        client_id: str = OAUTH_CLIENT_ID,
    ) -> None:
        self._session = session
        self._tokens = tokens
        self._live_id = live_id
        self._client_id = client_id

    @property
    def tokens(self) -> dict[str, Any]:
        return self._tokens

    async def async_ensure_token(self) -> str:
        now = time.time()
        if now >= self._tokens["expires_at"] or now >= self._tokens["xsts_expires_at"]:
            await self._refresh_tokens()
        userhash = self._tokens["userhash"]
        xsts_token = self._tokens["xsts_token"]
        return f"XBL3.0 x={userhash};{xsts_token}"

    async def _refresh_tokens(self) -> None:
        refresh_payload = {
            "client_id": self._client_id,
            "refresh_token": self._tokens["refresh_token"],
            "grant_type": "refresh_token",
            "scope": OAUTH_SCOPES,
        }
        async with self._session.post(OAUTH_TOKEN_URL, data=refresh_payload) as resp:
            resp.raise_for_status()
            token_data = await resp.json()

        access_token = token_data["access_token"]
        self._tokens["access_token"] = access_token
        if "refresh_token" in token_data:
            self._tokens["refresh_token"] = token_data["refresh_token"]
        self._tokens["expires_at"] = time.time() + float(
            token_data.get("expires_in", 3600)
        )

        userhash, xsts_token = await _fetch_xsts_tokens(self._session, access_token)
        self._tokens["userhash"] = userhash
        self._tokens["xsts_token"] = xsts_token
        self._tokens["xsts_expires_at"] = time.time() + XSTS_LIFETIME

    async def async_installed_titles(self) -> list[Title]:
        auth = await self.async_ensure_token()
        url = (
            f"https://xccs.xboxlive.com/lists/installedApps"
            f"?deviceId={self._live_id}"
        )
        async with self._session.get(url, headers=_api_headers(auth)) as resp:
            resp.raise_for_status()
            payload = await resp.json()
        return parse_installed_apps(payload)

    async def async_active_aumid(self) -> str | None:
        auth = await self.async_ensure_token()
        url = f"https://xccs.xboxlive.com/consoles/{self._live_id}"
        async with self._session.get(url, headers=_api_headers(auth)) as resp:
            if resp.status == 404:
                status_url = (
                    f"https://xccs.xboxlive.com/consoles/{self._live_id}/status"
                )
                async with self._session.get(
                    status_url, headers=_api_headers(auth)
                ) as status_resp:
                    status_resp.raise_for_status()
                    payload = await status_resp.json()
            else:
                resp.raise_for_status()
                payload = await resp.json()
        return parse_active_aumid(payload)

    async def _send_command(
        self,
        command_type: str,
        command: str,
        parameters: list[dict[str, str]] | None = None,
    ) -> None:
        auth = await self.async_ensure_token()
        body = {
            "destination": "Xbox",
            "type": command_type,
            "command": command,
            "sessionId": str(uuid4()),
            "sourceId": "com.microsoft.smartglass",
            "parameters": parameters or [],
            "linkedDeviceId": self._live_id,
        }
        async with self._session.post(
            XBOX_COMMANDS_URL,
            headers=_api_headers(auth),
            json=body,
        ) as resp:
            resp.raise_for_status()

    async def async_turn_off(self) -> None:
        await self._send_command("Power", "TurnOff")

    async def async_go_home(self) -> None:
        await self._send_command("Shell", "GoHome")

    async def async_launch(self, launch_id: str) -> None:
        await self._send_command(
            "Shell",
            "Activate",
            [{"oneStoreProductId": launch_id}],
        )

"""Xbox title catalog parsing, OAuth helpers, and Network REST client."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from uuid import uuid4

from .const import (
    DASHBOARD_AUMID,
    DASHBOARD_PRODUCT_ID,
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
    content_type: str | None = None
    is_game: bool | None = None


@dataclass(frozen=True)
class SourceAction:
    kind: str  # "dashboard" | "launch" | "signin" | "unknown"
    launch_id: str | None = None


@dataclass(frozen=True)
class RemoteAction:
    kind: str  # "button" | "back" | "home" | "next" | "previous"
    value: str | None = None


@dataclass(frozen=True)
class SourceFilters:
    hide_dlc: bool = True
    hide_system_apps: bool = True
    favorites: tuple[str, ...] = ()


DLC_CONTENT_TYPES = frozenset({"dlc", "durable"})
SYSTEM_CONTENT_TYPES = frozenset({"system", "systemapp", "xboxsystem"})
SYSTEM_APP_NAMES = frozenset(
    {
        "Microsoft Store",
        "Xbox Accessory",
        "Television",
        "Settings",
        "Xbox Guide",
    }
)
HOMEKIT_TV_REMOTE_KEYS: dict[str, RemoteAction] = {
    "arrow_up": RemoteAction(kind="button", value="Up"),
    "arrow_down": RemoteAction(kind="button", value="Down"),
    "arrow_left": RemoteAction(kind="button", value="Left"),
    "arrow_right": RemoteAction(kind="button", value="Right"),
    "select": RemoteAction(kind="button", value="A"),
    "back": RemoteAction(kind="back"),
    "exit": RemoteAction(kind="home"),
    "information": RemoteAction(kind="button", value="Nexus"),
    "next_track": RemoteAction(kind="next"),
    "previous_track": RemoteAction(kind="previous"),
}


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
        content_type = item.get("contentType") or item.get("content_type")
        is_game = item.get("isGame")
        if is_game is None:
            is_game = item.get("is_game")
        titles.append(
            Title(
                name=name,
                launch_id=str(launch_id),
                aumid=aumid,
                content_type=content_type,
                is_game=is_game,
            )
        )
    return titles


def parse_active_aumid(status_payload: dict) -> str | None:
    for key in ("focusAppAumid", "focus_app_aumid"):
        value = status_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    nested = status_payload.get("status")
    if isinstance(nested, dict):
        for key in ("focusAppAumid", "focus_app_aumid"):
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return value
        active_titles = nested.get("activeTitles")
    else:
        active_titles = None
    if not active_titles:
        active_titles = status_payload.get("activeTitles")
    if not active_titles:
        return None
    first = active_titles[0]
    return first.get("aum") or first.get("aumid")


def is_dashboard_source(source: str) -> bool:
    return source.casefold() == DASHBOARD_SOURCE.casefold()


def launch_id_for_source(source: str, titles: list[Title]) -> str | None:
    if is_dashboard_source(source):
        return None
    needle = source.casefold()
    for title in titles:
        if title.name.casefold() == needle:
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


def parse_favorites(value: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = list(value)
    return tuple(part.strip() for part in parts if str(part).strip())


def resolve_homekit_tv_remote_key(key_name: str) -> RemoteAction | None:
    return HOMEKIT_TV_REMOTE_KEYS.get(key_name)


def _title_for_aumid(titles: list[Title], aumid: str | None) -> Title | None:
    if not aumid:
        return None
    for title in titles:
        if title.aumid == aumid:
            return title
    return None


def is_in_game(
    powered_on: bool,
    aumid: str | None,
    titles: list[Title],
) -> bool:
    if not powered_on or not aumid or aumid == DASHBOARD_AUMID:
        return False
    current = _title_for_aumid(titles, aumid)
    if current is None:
        return False
    if current.is_game is True:
        return True
    return (current.content_type or "").casefold() == "game"


def extra_media_attributes(
    *,
    powered_on: bool,
    aumid: str | None,
    titles: list[Title],
) -> dict[str, Any]:
    current = _title_for_aumid(titles, aumid)
    return {
        "app_id": aumid,
        "content_type": current.content_type if current else None,
        "in_game": is_in_game(powered_on, aumid, titles),
    }


def _content_type(title: Title) -> str:
    return (title.content_type or "").casefold()


def _is_hidden(title: Title, hide_dlc: bool, hide_system_apps: bool) -> bool:
    content_type = _content_type(title)
    if hide_dlc and content_type in DLC_CONTENT_TYPES:
        return True
    if hide_system_apps and (
        content_type in SYSTEM_CONTENT_TYPES or title.name in SYSTEM_APP_NAMES
    ):
        return True
    return False


def _matches_favorite(title: Title, favorite: str) -> bool:
    needle = favorite.casefold()
    return title.name.casefold() == needle or title.launch_id.casefold() == needle


def build_source_list(
    titles: list[Title],
    current_aumid: str | None,
    current_name: str | None,
    *,
    hide_dlc: bool = True,
    hide_system_apps: bool = True,
    favorites: tuple[str, ...] = (),
) -> list[str]:
    seen_launch_ids: set[str] = set()
    unique_titles: list[Title] = []
    for title in sorted(titles, key=lambda item: item.name.casefold()):
        if title.launch_id in seen_launch_ids:
            continue
        seen_launch_ids.add(title.launch_id)
        unique_titles.append(title)

    favorite_titles: list[Title] = []
    seen_favorite_ids: set[str] = set()
    for favorite in favorites:
        for title in unique_titles:
            if title.launch_id in seen_favorite_ids:
                continue
            if _matches_favorite(title, favorite):
                favorite_titles.append(title)
                seen_favorite_ids.add(title.launch_id)
                break

    ordered: list[Title] = list(favorite_titles)
    for title in unique_titles:
        if title.launch_id in seen_favorite_ids:
            continue
        if _is_hidden(title, hide_dlc, hide_system_apps):
            continue
        ordered.append(title)

    sources = [DASHBOARD_SOURCE]
    sources.extend(title.name for title in ordered)

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
    for title in favorite_titles:
        if len(truncated) >= MAX_SOURCES:
            break
        if title.name not in truncated:
            truncated.append(title.name)
    if (
        current_friendly
        and not is_dashboard_source(current_friendly)
        and current_friendly not in truncated
    ):
        if len(truncated) >= MAX_SOURCES:
            truncated[-1] = current_friendly
        else:
            truncated.append(current_friendly)
    for title in ordered:
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
    text = redirect_url.strip()
    if not text:
        return None
    if re.search(r"(?:^|[?&])error=", text):
        return None

    match = re.search(r"[?&]code=([^&\s\"'<>“”]+)", text)
    if match:
        return unquote(match.group(1).rstrip(".,;"))

    candidate = text
    host_path = candidate.split("?", 1)[0]
    if "://" not in host_path and host_path.lower().startswith("localhost"):
        candidate = f"http://{candidate}"
    parsed = urlparse(candidate)
    params = parse_qs(parsed.query)
    if params.get("error"):
        return None
    codes = params.get("code")
    if codes:
        return unquote(codes[0])
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
            "linkedXboxId": self._live_id,
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
        await self._send_command("Shell", "GoHome", [{}])
        await self.async_launch(DASHBOARD_PRODUCT_ID)

    async def async_go_back(self) -> None:
        await self._send_command("Shell", "GoBack")

    async def async_press_button(self, key_type: str) -> None:
        await self._send_command("Shell", "InjectKey", [{"keyType": key_type}])

    async def async_play(self) -> None:
        await self._send_command("Media", "Play")

    async def async_pause(self) -> None:
        await self._send_command("Media", "Pause")

    async def async_next(self) -> None:
        await self._send_command("Media", "Next")

    async def async_previous(self) -> None:
        await self._send_command("Media", "Previous")

    async def async_execute_remote_action(self, action: RemoteAction) -> None:
        kind = action.kind
        if kind == "button":
            if action.value is None:
                raise ValueError("button action requires a key type")
            await self.async_press_button(action.value)
            return
        if kind == "back":
            await self.async_go_back()
            return
        if kind == "home":
            await self.async_go_home()
            return
        if kind == "next":
            await self.async_next()
            return
        if kind == "previous":
            await self.async_previous()
            return
        _unhandled_remote_kind(kind)

    async def async_launch(self, launch_id: str) -> None:
        await self._send_command(
            "Shell",
            "ActivateApplicationWithOneStoreProductId",
            [{"oneStoreProductId": launch_id}],
        )


def _unhandled_remote_kind(kind: str) -> None:
    raise ValueError(f"Unhandled remote action kind: {kind}")

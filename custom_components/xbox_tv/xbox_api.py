"""Xbox title catalog parsing and OAuth URL helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse

from .const import (
    DASHBOARD_AUMID,
    DASHBOARD_SOURCE,
    MAX_SOURCES,
    OAUTH_AUTHORIZE_URL,
    OAUTH_SCOPES,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Title:
    name: str
    launch_id: str
    aumid: str | None = None


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

"""Coordinator state merge for Xbox TV (HA wrapper in Task 6)."""

from __future__ import annotations

from dataclasses import dataclass

from .const import DASHBOARD_SOURCE
from .smartglass import SmartGlassClient
from .xbox_api import (
    Title,
    XboxWebApiClient,
    build_source_list,
    friendly_source,
)

# Task 6: XboxTvCoordinator(DataUpdateCoordinator[XboxTvState]) with title
# refresh throttling via time.monotonic() and TITLE_REFRESH_INTERVAL.


@dataclass
class XboxTvState:
    powered_on: bool
    aumid: str | None
    titles: list[Title]
    source_list: list[str]
    source: str
    microsoft_connected: bool


async def async_fetch_state(
    smartglass: SmartGlassClient,
    webapi: XboxWebApiClient | None,
    titles_cache: list[Title],
) -> XboxTvState:
    powered_on = await smartglass.async_get_powered_on()
    aumid: str | None = None
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
    if powered_on and aumid:
        source = friendly_source(titles, aumid)
    else:
        source = DASHBOARD_SOURCE

    return XboxTvState(
        powered_on=powered_on,
        aumid=aumid,
        titles=titles,
        source_list=source_list,
        source=source,
        microsoft_connected=microsoft_connected,
    )

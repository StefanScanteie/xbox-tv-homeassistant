"""Coordinator state merge for Xbox TV (HA wrapper in Task 6)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from .const import (
    CONF_CLIENT_ID,
    CONF_LIVE_ID,
    CONF_TOKENS,
    DASHBOARD_SOURCE,
    DOMAIN,
    OAUTH_CLIENT_ID,
    SCAN_INTERVAL,
    TITLE_REFRESH_INTERVAL,
)
from .smartglass import SmartGlassClient
from .xbox_api import (
    Title,
    XboxWebApiClient,
    build_source_list,
    friendly_source,
)

_LOGGER = logging.getLogger(__name__)

try:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

    HAS_HA = True
except ImportError:
    HAS_HA = False


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


class _CachedTitlesWebApi:
    """Web API wrapper that returns coordinator-managed title cache."""

    def __init__(
        self,
        webapi: XboxWebApiClient,
        titles_cache: list[Title],
    ) -> None:
        self._webapi = webapi
        self._titles_cache = titles_cache

    async def async_active_aumid(self) -> str | None:
        return await self._webapi.async_active_aumid()

    async def async_installed_titles(self) -> list[Title]:
        return self._titles_cache


if HAS_HA:

    class XboxTvCoordinator(DataUpdateCoordinator[XboxTvState]):
        """Coordinator for Xbox TV state updates."""

        def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
            """Initialize the coordinator."""
            super().__init__(
                hass,
                _LOGGER,
                name=DOMAIN,
                update_interval=timedelta(seconds=SCAN_INTERVAL),
            )
            self._entry = entry
            self._smartglass = SmartGlassClient(
                entry.data["host"],
                entry.data[CONF_LIVE_ID],
            )
            session = async_get_clientsession(hass)
            tokens = entry.data.get(CONF_TOKENS)
            client_id = entry.data.get(CONF_CLIENT_ID, OAUTH_CLIENT_ID)
            self._webapi: XboxWebApiClient | None = None
            if tokens is not None:
                self._webapi = XboxWebApiClient(
                    session,
                    tokens,
                    entry.data[CONF_LIVE_ID],
                    client_id,
                )
            self._titles_cache: list[Title] = []
            self._last_title_refresh = 0.0

        @property
        def smartglass(self) -> SmartGlassClient:
            """Return the SmartGlass client."""
            return self._smartglass

        @property
        def webapi(self) -> XboxWebApiClient | None:
            """Return the Xbox web API client."""
            return self._webapi

        async def _async_update_data(self) -> XboxTvState:
            """Fetch the latest state."""
            tokens_before: dict[str, Any] | None = None
            if self._webapi is not None:
                tokens_before = dict(self._webapi.tokens)

            now = time.monotonic()
            if self._webapi is not None and (
                not self._titles_cache
                or now - self._last_title_refresh >= TITLE_REFRESH_INTERVAL
            ):
                try:
                    self._titles_cache = await self._webapi.async_installed_titles()
                    self._last_title_refresh = now
                except Exception:
                    _LOGGER.debug("Title catalog refresh failed", exc_info=True)

            webapi_for_fetch: XboxWebApiClient | _CachedTitlesWebApi | None
            if self._webapi is not None:
                webapi_for_fetch = _CachedTitlesWebApi(
                    self._webapi,
                    self._titles_cache,
                )
            else:
                webapi_for_fetch = None

            state = await async_fetch_state(
                self._smartglass,
                webapi_for_fetch,
                self._titles_cache,
            )

            if (
                self._webapi is not None
                and tokens_before is not None
                and self._webapi.tokens != tokens_before
            ):
                self.hass.config_entries.async_update_entry(
                    self._entry,
                    data={**self._entry.data, CONF_TOKENS: self._webapi.tokens},
                )

            return state

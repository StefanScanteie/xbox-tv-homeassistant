from __future__ import annotations

import pytest

from xbox_tv.const import DASHBOARD_AUMID, DASHBOARD_SOURCE
from xbox_tv.coordinator import XboxTvState, async_fetch_state
from xbox_tv.xbox_api import Title


class FakeSmartGlass:
    def __init__(self, powered_on: bool) -> None:
        self._powered_on = powered_on

    async def async_get_powered_on(self) -> bool:
        return self._powered_on


class FakeWebApi:
    def __init__(
        self,
        *,
        aumid: str | None = None,
        titles: list[Title] | None = None,
        aumid_error: Exception | None = None,
        titles_error: Exception | None = None,
    ) -> None:
        self._aumid = aumid
        self._titles = titles or []
        self._aumid_error = aumid_error
        self._titles_error = titles_error

    async def async_active_aumid(self) -> str | None:
        if self._aumid_error is not None:
            raise self._aumid_error
        return self._aumid

    async def async_installed_titles(self) -> list[Title]:
        if self._titles_error is not None:
            raise self._titles_error
        return self._titles


NETFLIX = Title(name="Netflix", launch_id="9WZDNCRFJ3TJ", aumid="Netflix.App")
HALO = Title(name="Halo Infinite", launch_id="9PP5G15W52VT", aumid="Halo.Infinite")


@pytest.mark.asyncio
async def test_fetch_state_powered_on_with_active_title() -> None:
    smartglass = FakeSmartGlass(True)
    webapi = FakeWebApi(aumid="Netflix.App", titles=[NETFLIX, HALO])
    cache: list[Title] = []

    state = await async_fetch_state(smartglass, webapi, cache)

    assert state == XboxTvState(
        powered_on=True,
        aumid="Netflix.App",
        titles=[NETFLIX, HALO],
        source_list=[DASHBOARD_SOURCE, "Halo Infinite", "Netflix"],
        source="Netflix",
        microsoft_connected=True,
    )


@pytest.mark.asyncio
async def test_fetch_state_powered_off_uses_dashboard_source() -> None:
    smartglass = FakeSmartGlass(False)
    webapi = FakeWebApi(aumid="Netflix.App", titles=[NETFLIX])
    cache: list[Title] = []

    state = await async_fetch_state(smartglass, webapi, cache)

    assert state.powered_on is False
    assert state.source == DASHBOARD_SOURCE
    assert state.aumid == "Netflix.App"


@pytest.mark.asyncio
async def test_fetch_state_unreachable_is_off_not_error() -> None:
    smartglass = FakeSmartGlass(False)
    webapi = FakeWebApi(aumid="Netflix.App", titles=[NETFLIX])

    state = await async_fetch_state(smartglass, webapi, [])

    assert state.powered_on is False
    assert state.source == DASHBOARD_SOURCE


@pytest.mark.asyncio
async def test_fetch_state_no_webapi_uses_cache() -> None:
    smartglass = FakeSmartGlass(True)
    cache = [NETFLIX]

    state = await async_fetch_state(smartglass, None, cache)

    assert state == XboxTvState(
        powered_on=True,
        aumid=None,
        titles=cache,
        source_list=[DASHBOARD_SOURCE, "Netflix"],
        source=DASHBOARD_SOURCE,
        microsoft_connected=False,
    )


@pytest.mark.asyncio
async def test_fetch_state_webapi_failure_keeps_titles_cache() -> None:
    smartglass = FakeSmartGlass(True)
    cache = [NETFLIX]
    webapi = FakeWebApi(
        aumid="Netflix.App",
        titles_error=RuntimeError("network down"),
    )

    state = await async_fetch_state(smartglass, webapi, cache)

    assert state.titles is cache
    assert state.aumid == "Netflix.App"
    assert state.source == "Netflix"
    assert state.microsoft_connected is True


@pytest.mark.asyncio
async def test_fetch_state_aumid_failure_still_returns_state() -> None:
    smartglass = FakeSmartGlass(True)
    cache = [NETFLIX]
    webapi = FakeWebApi(
        aumid_error=RuntimeError("status unavailable"),
        titles=[HALO],
    )

    state = await async_fetch_state(smartglass, webapi, cache)

    assert state.aumid is None
    assert state.titles == [HALO]
    assert state.source == DASHBOARD_SOURCE
    assert state.powered_on is True


@pytest.mark.asyncio
async def test_fetch_state_dashboard_aumid_when_on() -> None:
    smartglass = FakeSmartGlass(True)
    webapi = FakeWebApi(aumid=DASHBOARD_AUMID, titles=[NETFLIX])

    state = await async_fetch_state(smartglass, webapi, [])

    assert state.source == DASHBOARD_SOURCE

from __future__ import annotations

import logging
import time

import pytest

from xbox_tv.const import (
    DASHBOARD_AUMID,
    DASHBOARD_SOURCE,
    MAX_SOURCES,
    OAUTH_TOKEN_URL,
)
from xbox_tv.xbox_api import (
    XBOX_USER_AUTH_URL,
    XBOX_XSTS_AUTH_URL,
    RemoteAction,
    Title,
    XboxWebApiClient,
    build_source_list,
    extra_media_attributes,
    extract_oauth_code,
    friendly_source,
    is_dashboard_source,
    is_in_game,
    launch_id_for_source,
    parse_active_aumid,
    parse_favorites,
    parse_installed_apps,
    resolve_homekit_tv_remote_key,
)


class FakeResponse:
    def __init__(self, status: int, json_data: dict | list | None = None) -> None:
        self.status = status
        self._json = json_data if json_data is not None else {}

    async def json(self) -> dict | list:
        return self._json

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(self.status)


class FakeSession:
    def __init__(self, mapping: dict[tuple[str, str], FakeResponse]) -> None:
        self.mapping = mapping
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        matches = [
            (prefix, resp)
            for (m, prefix), resp in self.mapping.items()
            if method == m and url.startswith(prefix)
        ]
        if matches:
            _, resp = max(matches, key=lambda item: len(item[0]))
            return resp
        return FakeResponse(404, {})

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        return self.request("POST", url, **kwargs)


LIVE_ID = "ABCDEF1234567890"


def _valid_tokens() -> dict:
    future = time.time() + 3600
    return {
        "access_token": "access",
        "refresh_token": "refresh",
        "expires_at": future,
        "userhash": "userhash123",
        "xsts_token": "xsts456",
        "xsts_expires_at": future,
    }


def _auth_headers(auth: str) -> dict:
    return {
        "Authorization": auth,
        "skillplatform": "RemoteManagement",
        "x-xbl-contract-version": "4",
        "Content-Type": "application/json",
    }


def _command_calls(session: FakeSession) -> list[dict]:
    return [
        kwargs["json"]
        for method, url, kwargs in session.calls
        if method == "POST" and url.startswith("https://xccs.xboxlive.com/commands")
    ]

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


@pytest.fixture
def titles() -> list[Title]:
    return parse_installed_apps(APPS)


def test_parse_installed_apps_skips_invalid_entries(titles: list[Title]) -> None:
    assert len(titles) == 2
    assert titles[0].name == "Netflix"
    assert titles[0].launch_id == "9WZDNCRFJ3TJ"
    assert titles[0].aumid == "Netflix.App"
    assert titles[1].name == "Halo Infinite"
    assert titles[1].launch_id == "9PP5G15W52VT"


def test_build_source_list_alphabetical(titles: list[Title]) -> None:
    assert build_source_list(titles, None, None) == [
        DASHBOARD_SOURCE,
        "Halo Infinite",
        "Netflix",
    ]


def test_build_source_list_deduplicates_launch_ids() -> None:
    dup_titles = [
        Title(name="Netflix A", launch_id="9WZDNCRFJ3TJ", aumid="Netflix.A"),
        Title(name="Netflix B", launch_id="9WZDNCRFJ3TJ", aumid="Netflix.B"),
        Title(name="Halo Infinite", launch_id="9PP5G15W52VT", aumid="Halo.Infinite"),
    ]
    assert build_source_list(dup_titles, None, None) == [
        DASHBOARD_SOURCE,
        "Halo Infinite",
        "Netflix A",
    ]


def test_build_source_list_appends_current_name_when_missing_from_catalog() -> None:
    assert build_source_list([], "Unknown.App", "Mystery Game") == [
        DASHBOARD_SOURCE,
        "Mystery Game",
    ]


def test_build_source_list_empty_catalog() -> None:
    assert build_source_list([], None, None) == [DASHBOARD_SOURCE]


def test_build_source_list_dashboard_aumid_without_name() -> None:
    assert build_source_list([], DASHBOARD_AUMID, None) == [DASHBOARD_SOURCE]


def test_build_source_list_truncates_to_max_sources(
    caplog: pytest.LogCaptureFixture,
) -> None:
    many_titles = [
        Title(name=f"Title {index:03d}", launch_id=f"id-{index:03d}")
        for index in range(120)
    ]
    current_aumid = "id-119"
    current_name = "Title 119"

    with caplog.at_level(logging.WARNING):
        sources = build_source_list(many_titles, current_aumid, current_name)

    assert len(sources) == MAX_SOURCES
    assert sources[0] == DASHBOARD_SOURCE
    assert current_name in sources
    assert "truncat" in caplog.text.lower()


def test_launch_id_for_source(titles: list[Title]) -> None:
    assert launch_id_for_source("Netflix", titles) == "9WZDNCRFJ3TJ"
    assert launch_id_for_source("netflix", titles) == "9WZDNCRFJ3TJ"
    assert launch_id_for_source(DASHBOARD_SOURCE, titles) is None


def test_is_dashboard_source() -> None:
    assert is_dashboard_source(DASHBOARD_SOURCE) is True
    assert is_dashboard_source("Netflix") is False


def test_friendly_source_dashboard_aumid(titles: list[Title]) -> None:
    assert friendly_source(titles, DASHBOARD_AUMID) == DASHBOARD_SOURCE
    assert friendly_source(titles, None) == DASHBOARD_SOURCE


def test_parse_active_aumid_prefers_status_active_titles() -> None:
    payload = {
        "status": {
            "activeTitles": [{"aum": "Netflix.App", "aumid": "Netflix.AppAlt"}]
        }
    }
    assert parse_active_aumid(payload) == "Netflix.App"


def test_parse_active_aumid_falls_back_to_top_level() -> None:
    payload = {"activeTitles": [{"aumid": "Halo.Infinite"}]}
    assert parse_active_aumid(payload) == "Halo.Infinite"


def test_parse_active_aumid_uses_focus_app_aumid() -> None:
    payload = {
        "focusAppAumid": "Netflix.App",
        "powerState": "On",
        "status": {"errorCode": "OK"},
    }
    assert parse_active_aumid(payload) == "Netflix.App"


def test_extract_oauth_code_success() -> None:
    assert (
        extract_oauth_code("http://localhost/auth/callback?code=ABC&lc=1033") == "ABC"
    )


def test_extract_oauth_code_error() -> None:
    assert (
        extract_oauth_code("http://localhost/auth/callback?error=access_denied")
        is None
    )


def test_extract_oauth_code_accepts_safari_address_without_scheme() -> None:
    assert (
        extract_oauth_code("localhost/auth/callback?code=M.C516_BAY.2.U.MsaArtifacts")
        == "M.C516_BAY.2.U.MsaArtifacts"
    )


def test_extract_oauth_code_from_safari_error_text() -> None:
    blob = (
        'Safari can’t open the page “localhost/auth/callback?code=M.C516_BAY.2.U.MsaArtifacts.abc%24” '
        "because Safari can’t connect to the server “localhost”."
    )
    assert extract_oauth_code(blob) == "M.C516_BAY.2.U.MsaArtifacts.abc$"


@pytest.mark.asyncio
async def test_async_installed_titles() -> None:
    session = FakeSession(
        {
            (
                "GET",
                f"https://xccs.xboxlive.com/lists/installedApps?deviceId={LIVE_ID}",
            ): FakeResponse(200, APPS),
        }
    )
    client = XboxWebApiClient(session, _valid_tokens(), LIVE_ID)
    titles = await client.async_installed_titles()

    assert len(titles) == 2
    assert titles[0].name == "Netflix"
    assert len(session.calls) == 1
    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert f"deviceId={LIVE_ID}" in url
    assert kwargs["headers"] == _auth_headers("XBL3.0 x=userhash123;xsts456")


@pytest.mark.asyncio
async def test_async_active_aumid_from_console() -> None:
    payload = {"status": {"activeTitles": [{"aum": "Netflix.App"}]}}
    session = FakeSession(
        {
            ("GET", f"https://xccs.xboxlive.com/consoles/{LIVE_ID}"): FakeResponse(
                200, payload
            ),
        }
    )
    client = XboxWebApiClient(session, _valid_tokens(), LIVE_ID)
    assert await client.async_active_aumid() == "Netflix.App"
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_async_active_aumid_falls_back_to_status() -> None:
    payload = {"activeTitles": [{"aumid": "Halo.Infinite"}]}
    session = FakeSession(
        {
            ("GET", f"https://xccs.xboxlive.com/consoles/{LIVE_ID}"): FakeResponse(
                404, {}
            ),
            (
                "GET",
                f"https://xccs.xboxlive.com/consoles/{LIVE_ID}/status",
            ): FakeResponse(200, payload),
        }
    )
    client = XboxWebApiClient(session, _valid_tokens(), LIVE_ID)
    assert await client.async_active_aumid() == "Halo.Infinite"
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_async_turn_off_command_body() -> None:
    session = FakeSession(
        {
            ("POST", "https://xccs.xboxlive.com/commands"): FakeResponse(200, {}),
        }
    )
    client = XboxWebApiClient(session, _valid_tokens(), LIVE_ID)
    await client.async_turn_off()

    commands = _command_calls(session)
    assert len(commands) == 1
    body = commands[0]
    assert body["type"] == "Power"
    assert body["command"] == "TurnOff"
    assert body["destination"] == "Xbox"
    assert body["sourceId"] == "com.microsoft.smartglass"
    assert body["linkedDeviceId"] == LIVE_ID
    assert body["linkedXboxId"] == LIVE_ID
    assert body["parameters"] == []


@pytest.mark.asyncio
async def test_async_launch_command_body() -> None:
    session = FakeSession(
        {
            ("POST", "https://xccs.xboxlive.com/commands"): FakeResponse(200, {}),
        }
    )
    client = XboxWebApiClient(session, _valid_tokens(), LIVE_ID)
    await client.async_launch("9WZDNCRFJ3TJ")

    commands = _command_calls(session)
    assert len(commands) == 1
    body = commands[0]
    assert body["type"] == "Shell"
    assert body["command"] == "ActivateApplicationWithOneStoreProductId"
    assert body["parameters"] == [{"oneStoreProductId": "9WZDNCRFJ3TJ"}]
    assert body["linkedXboxId"] == LIVE_ID
    assert body["linkedDeviceId"] == LIVE_ID


@pytest.mark.asyncio
async def test_async_ensure_token_refreshes_expired_tokens() -> None:
    expired_tokens = {
        "access_token": "old_access",
        "refresh_token": "refresh",
        "expires_at": 0.0,
        "userhash": "old_userhash",
        "xsts_token": "old_xsts",
        "xsts_expires_at": 0.0,
    }
    session = FakeSession(
        {
            ("POST", OAUTH_TOKEN_URL): FakeResponse(
                200,
                {
                    "access_token": "new_access",
                    "refresh_token": "new_refresh",
                    "expires_in": 3600,
                },
            ),
            ("POST", XBOX_USER_AUTH_URL): FakeResponse(
                200,
                {
                    "Token": "user_jwt",
                    "DisplayClaims": {"xui": [{"uhs": "new_userhash"}]},
                },
            ),
            ("POST", XBOX_XSTS_AUTH_URL): FakeResponse(
                200,
                {"Token": "new_xsts"},
            ),
        }
    )
    client = XboxWebApiClient(session, expired_tokens, LIVE_ID)
    auth = await client.async_ensure_token()

    assert auth == "XBL3.0 x=new_userhash;new_xsts"
    assert client.tokens["access_token"] == "new_access"
    assert client.tokens["refresh_token"] == "new_refresh"
    assert client.tokens["userhash"] == "new_userhash"
    assert client.tokens["xsts_token"] == "new_xsts"
    assert client.tokens["expires_at"] > time.time()
    assert client.tokens["xsts_expires_at"] > time.time()
    refresh_calls = [call for call in session.calls if call[0] == "POST" and call[1].startswith(OAUTH_TOKEN_URL)]
    assert len(refresh_calls) == 1
    assert refresh_calls[0][2]["data"]["grant_type"] == "refresh_token"


@pytest.mark.asyncio
async def test_async_go_home_command_body() -> None:
    session = FakeSession(
        {
            ("POST", "https://xccs.xboxlive.com/commands"): FakeResponse(200, {}),
        }
    )
    client = XboxWebApiClient(session, _valid_tokens(), LIVE_ID)
    await client.async_go_home()

    commands = _command_calls(session)
    assert len(commands) == 1
    body = commands[0]
    assert body["type"] == "Shell"
    assert body["command"] == "ActivateApplicationWithOneStoreProductId"
    assert body["parameters"] == [{"oneStoreProductId": DASHBOARD_AUMID}]


def test_parse_installed_apps_maps_content_type_and_is_game() -> None:
    titles = parse_installed_apps(
        {
            "result": [
                {
                    "name": "Halo Infinite",
                    "oneStoreProductId": "9PNJSS9MW5HV",
                    "aumid": "Microsoft.HaloInfinite_8wekyb3d8bbwe!HaloInfinite",
                    "contentType": "Game",
                    "isGame": True,
                },
                {
                    "name": "Season Pass",
                    "oneStoreProductId": "9NTESTDLC",
                    "aumid": "Microsoft.Dlc_8wekyb3d8bbwe!Dlc",
                    "contentType": "Dlc",
                    "isGame": False,
                },
            ]
        }
    )
    assert titles[0].content_type == "Game"
    assert titles[0].is_game is True
    assert titles[1].content_type == "Dlc"
    assert titles[1].is_game is False


def test_build_source_list_hides_dlc_by_default() -> None:
    titles = [
        Title(name="Halo Infinite", launch_id="1", content_type="Game", is_game=True),
        Title(name="Season Pass", launch_id="2", content_type="Dlc", is_game=False),
        Title(name="Durable Extra", launch_id="3", content_type="Durable"),
    ]
    assert build_source_list(titles, None, None) == [
        DASHBOARD_SOURCE,
        "Halo Infinite",
    ]


def test_build_source_list_hides_system_apps_by_default() -> None:
    titles = [
        Title(name="Netflix", launch_id="1", content_type="App"),
        Title(name="Microsoft Store", launch_id="2", content_type="App"),
        Title(name="Settings", launch_id="3", content_type="SystemApp"),
    ]
    assert build_source_list(titles, None, None) == [DASHBOARD_SOURCE, "Netflix"]


def test_build_source_list_can_keep_dlc_and_system_apps() -> None:
    titles = [
        Title(name="Season Pass", launch_id="2", content_type="Dlc"),
        Title(name="Microsoft Store", launch_id="3", content_type="App"),
    ]
    assert build_source_list(
        titles, None, None, hide_dlc=False, hide_system_apps=False
    ) == [DASHBOARD_SOURCE, "Microsoft Store", "Season Pass"]


def test_build_source_list_keeps_current_even_when_filtered() -> None:
    titles = [
        Title(
            name="Season Pass",
            launch_id="2",
            aumid="aumid.dlc",
            content_type="Dlc",
        )
    ]
    sources = build_source_list(titles, "aumid.dlc", None)
    assert sources == [DASHBOARD_SOURCE, "Season Pass"]


def test_build_source_list_pins_favorites_after_dashboard() -> None:
    titles = [
        Title(name="Apple TV", launch_id="a"),
        Title(name="Halo Infinite", launch_id="h"),
        Title(name="Netflix", launch_id="n"),
        Title(name="YouTube", launch_id="y"),
    ]
    sources = build_source_list(titles, None, None, favorites=("Netflix", "h"))
    assert sources == [
        DASHBOARD_SOURCE,
        "Netflix",
        "Halo Infinite",
        "Apple TV",
        "YouTube",
    ]


def test_build_source_list_favorites_override_filters() -> None:
    titles = [
        Title(name="Halo Infinite", launch_id="h", content_type="Game"),
        Title(name="Season Pass", launch_id="d", content_type="Dlc"),
    ]
    sources = build_source_list(titles, None, None, favorites=("Season Pass",))
    assert sources == [DASHBOARD_SOURCE, "Season Pass", "Halo Infinite"]


def test_extra_media_attributes_exposes_aumid_and_content_type() -> None:
    titles = [
        Title(
            name="Halo Infinite",
            launch_id="9PNJSS9MW5HV",
            aumid="Microsoft.HaloInfinite_8wekyb3d8bbwe!HaloInfinite",
            content_type="Game",
            is_game=True,
        )
    ]
    assert extra_media_attributes(
        powered_on=True,
        aumid="Microsoft.HaloInfinite_8wekyb3d8bbwe!HaloInfinite",
        titles=titles,
    ) == {
        "app_id": "Microsoft.HaloInfinite_8wekyb3d8bbwe!HaloInfinite",
        "content_type": "Game",
        "in_game": True,
    }


def test_is_in_game_false_on_dashboard() -> None:
    assert (
        is_in_game(
            powered_on=True,
            aumid=DASHBOARD_AUMID,
            titles=[],
        )
        is False
    )


def test_is_in_game_false_when_off() -> None:
    titles = [
        Title(
            name="Halo Infinite",
            launch_id="1",
            aumid="Microsoft.HaloInfinite_8wekyb3d8bbwe!HaloInfinite",
            content_type="Game",
            is_game=True,
        )
    ]
    assert (
        is_in_game(
            powered_on=False,
            aumid="Microsoft.HaloInfinite_8wekyb3d8bbwe!HaloInfinite",
            titles=titles,
        )
        is False
    )


def test_resolve_homekit_tv_remote_keys() -> None:
    assert resolve_homekit_tv_remote_key("arrow_up") == RemoteAction(
        kind="button", value="Up"
    )
    assert resolve_homekit_tv_remote_key("arrow_down") == RemoteAction(
        kind="button", value="Down"
    )
    assert resolve_homekit_tv_remote_key("arrow_left") == RemoteAction(
        kind="button", value="Left"
    )
    assert resolve_homekit_tv_remote_key("arrow_right") == RemoteAction(
        kind="button", value="Right"
    )
    assert resolve_homekit_tv_remote_key("select") == RemoteAction(
        kind="button", value="A"
    )
    assert resolve_homekit_tv_remote_key("back") == RemoteAction(kind="back")
    assert resolve_homekit_tv_remote_key("exit") == RemoteAction(kind="home")
    assert resolve_homekit_tv_remote_key("information") == RemoteAction(
        kind="button", value="Nexus"
    )
    assert resolve_homekit_tv_remote_key("next_track") == RemoteAction(kind="next")
    assert resolve_homekit_tv_remote_key("previous_track") == RemoteAction(
        kind="previous"
    )
    assert resolve_homekit_tv_remote_key("play_pause") is None
    assert resolve_homekit_tv_remote_key("unknown") is None


def test_parse_favorites_splits_comma_separated_names() -> None:
    assert parse_favorites("Netflix, Halo Infinite") == ("Netflix", "Halo Infinite")
    assert parse_favorites(["YouTube", "  Disney+ "]) == ("YouTube", "Disney+")
    assert parse_favorites(None) == ()
    assert parse_favorites("") == ()


async def _command_client() -> tuple[FakeSession, XboxWebApiClient]:
    session = FakeSession(
        {
            ("POST", "https://xccs.xboxlive.com/commands"): FakeResponse(200, {}),
        }
    )
    return session, XboxWebApiClient(session, _valid_tokens(), LIVE_ID)


@pytest.mark.asyncio
async def test_async_play_pause_next_previous_command_bodies() -> None:
    session, client = await _command_client()
    await client.async_play()
    await client.async_pause()
    await client.async_next()
    await client.async_previous()

    commands = _command_calls(session)
    assert [body["type"] for body in commands] == ["Media", "Media", "Media", "Media"]
    assert [body["command"] for body in commands] == [
        "Play",
        "Pause",
        "Next",
        "Previous",
    ]
    assert all(body["parameters"] == [] for body in commands)


@pytest.mark.asyncio
async def test_async_go_back_command_body() -> None:
    session, client = await _command_client()
    await client.async_go_back()

    body = _command_calls(session)[0]
    assert body["type"] == "Shell"
    assert body["command"] == "GoBack"
    assert body["parameters"] == []


@pytest.mark.asyncio
async def test_async_press_button_command_body() -> None:
    session, client = await _command_client()
    await client.async_press_button("Up")

    body = _command_calls(session)[0]
    assert body["type"] == "Shell"
    assert body["command"] == "InjectKey"
    assert body["parameters"] == [{"keyType": "Up"}]


@pytest.mark.asyncio
async def test_async_execute_remote_action_dispatches() -> None:
    session, client = await _command_client()
    await client.async_execute_remote_action(RemoteAction(kind="button", value="A"))
    await client.async_execute_remote_action(RemoteAction(kind="back"))
    await client.async_execute_remote_action(RemoteAction(kind="home"))
    await client.async_execute_remote_action(RemoteAction(kind="next"))
    await client.async_execute_remote_action(RemoteAction(kind="previous"))

    commands = _command_calls(session)
    assert [(body["type"], body["command"]) for body in commands] == [
        ("Shell", "InjectKey"),
        ("Shell", "GoBack"),
        ("Shell", "ActivateApplicationWithOneStoreProductId"),
        ("Media", "Next"),
        ("Media", "Previous"),
    ]
    assert commands[2]["parameters"] == [{"oneStoreProductId": DASHBOARD_AUMID}]
    assert commands[0]["parameters"] == [{"keyType": "A"}]

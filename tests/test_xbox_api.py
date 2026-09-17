from __future__ import annotations

import logging

import pytest

from xbox_tv.const import DASHBOARD_AUMID, DASHBOARD_SOURCE, MAX_SOURCES
from xbox_tv.xbox_api import (
    Title,
    build_source_list,
    extract_oauth_code,
    friendly_source,
    is_dashboard_source,
    launch_id_for_source,
    parse_active_aumid,
    parse_installed_apps,
)

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


def test_extract_oauth_code_success() -> None:
    assert (
        extract_oauth_code("http://localhost/auth/callback?code=ABC&lc=1033") == "ABC"
    )


def test_extract_oauth_code_error() -> None:
    assert (
        extract_oauth_code("http://localhost/auth/callback?error=access_denied")
        is None
    )

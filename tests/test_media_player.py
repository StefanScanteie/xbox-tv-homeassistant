from __future__ import annotations

from xbox_tv.const import DASHBOARD_SOURCE
from xbox_tv.xbox_api import SourceAction, Title, resolve_source_action

NETFLIX = Title(name="Netflix", launch_id="9WZDNCRFJ3TJ", aumid="Netflix.App")
HALO = Title(name="Halo Infinite", launch_id="9PP5G15W52VT", aumid="Halo.Infinite")

NETFLIX = Title(name="Netflix", launch_id="9WZDNCRFJ3TJ", aumid="Netflix.App")
HALO = Title(name="Halo Infinite", launch_id="9PP5G15W52VT", aumid="Halo.Infinite")


def test_resolve_source_action_dashboard() -> None:
    assert resolve_source_action(DASHBOARD_SOURCE, [NETFLIX], True) == SourceAction(
        "dashboard"
    )
    assert resolve_source_action(DASHBOARD_SOURCE, [], False) == SourceAction(
        "dashboard"
    )


def test_resolve_source_action_known_title_with_microsoft() -> None:
    assert resolve_source_action("Netflix", [NETFLIX, HALO], True) == SourceAction(
        "launch", "9WZDNCRFJ3TJ"
    )


def test_resolve_source_action_unknown_with_microsoft() -> None:
    assert resolve_source_action("Mystery Game", [NETFLIX], True) == SourceAction(
        "unknown"
    )


def test_resolve_source_action_non_dashboard_without_microsoft() -> None:
    assert resolve_source_action("Netflix", [NETFLIX], False) == SourceAction(
        "signin"
    )


def test_resolve_source_action_unknown_without_microsoft() -> None:
    assert resolve_source_action("Mystery Game", [], False) == SourceAction("signin")


def test_media_player_exposes_remote_and_media_controls() -> None:
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "xbox_tv"
        / "media_player.py"
    ).read_text()
    assert "EVENT_HOMEKIT_TV_REMOTE_KEY_PRESSED" in text
    assert "MediaPlayerEntityFeature.PLAY" in text
    assert "MediaPlayerEntityFeature.PAUSE" in text
    assert "MediaPlayerEntityFeature.PLAY_PAUSE" in text
    assert "MediaPlayerEntityFeature.NEXT_TRACK" in text
    assert "MediaPlayerEntityFeature.PREVIOUS_TRACK" in text
    assert "async def async_media_play" in text
    assert "async def async_media_pause" in text
    assert "async def async_media_play_pause" in text
    assert "async def async_media_next_track" in text
    assert "async def async_media_previous_track" in text
    assert "extra_state_attributes" in text

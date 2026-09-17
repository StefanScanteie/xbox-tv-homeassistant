from __future__ import annotations

from xbox_tv.const import DASHBOARD_SOURCE
from xbox_tv.xbox_api import SourceAction, Title, resolve_source_action

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

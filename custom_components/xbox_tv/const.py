"""Constants for the Xbox TV integration."""

from __future__ import annotations

import re

DOMAIN = "xbox_tv"
DEFAULT_NAME = "Xbox"
CONF_LIVE_ID = "live_id"
CONF_TOKENS = "tokens"
CONF_CLIENT_ID = "client_id"

SMARTGLASS_PORT = 5050
POLL_TIMEOUT = 5.0
SCAN_INTERVAL = 10
TITLE_REFRESH_INTERVAL = 900
TURN_ON_WAIT = 30
LAUNCH_WAIT = 30

DASHBOARD_SOURCE = "Dashboard"
DASHBOARD_AUMID = "Xbox.Dashboard_8wekyb3d8bbwe!Xbox.Dashboard.Application"
MAX_SOURCES = 100
PLATFORMS = ("media_player", "binary_sensor")

CONF_HIDE_DLC = "hide_dlc"
CONF_HIDE_SYSTEM_APPS = "hide_system_apps"
CONF_FAVORITES = "favorites"
EVENT_HOMEKIT_TV_REMOTE_KEY_PRESSED = "homekit_tv_remote_key_pressed"

OAUTH_CLIENT_ID = "388ea51c-0b25-4029-aae2-17df49d23905"
OAUTH_REDIRECT_URI = "http://localhost/auth/callback"
OAUTH_SCOPES = "XboxLive.signin XboxLive.offline_access"
OAUTH_AUTHORIZE_URL = "https://login.live.com/oauth20_authorize.srf"
OAUTH_TOKEN_URL = "https://login.live.com/oauth20_token.srf"

LIVE_ID_RE = re.compile(r"^[A-Fa-f0-9]{8,32}$")


def is_valid_host(host: str) -> bool:
    return bool(host.strip())


def is_valid_live_id(live_id: str) -> bool:
    return bool(LIVE_ID_RE.fullmatch(live_id.strip()))

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from xbox_tv.const import (
    DOMAIN,
    MAX_SOURCES,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPES,
)
from xbox_tv.xbox_api import build_authorize_url


def test_authorize_url_includes_client_and_redirect() -> None:
    url = build_authorize_url(OAUTH_CLIENT_ID, OAUTH_REDIRECT_URI)
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert "login.live.com" in parsed.netloc
    assert params["client_id"] == [OAUTH_CLIENT_ID]
    assert params["redirect_uri"] == [OAUTH_REDIRECT_URI]
    assert params["response_type"] == ["code"]
    assert params["scope"] == [OAUTH_SCOPES]


def test_max_sources_constant() -> None:
    assert MAX_SOURCES == 100


def test_domain_constant() -> None:
    assert DOMAIN == "xbox_tv"

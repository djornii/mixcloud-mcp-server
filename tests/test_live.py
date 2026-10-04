"""Tests that hit the real Mixcloud API.

They need a token and are skipped unless MIXCLOUD_LIVE=1, so `uv run pytest` stays
offline and credential-free:

    MIXCLOUD_LIVE=1 MIXCLOUD_TOKEN=... uv run pytest -m live
"""

import os

import pytest

from mixcloud_mcp_server import client
from mixcloud_mcp_server.tools import oauth, read


def require_live() -> None:
    if os.getenv("MIXCLOUD_LIVE") != "1":
        pytest.skip("set MIXCLOUD_LIVE=1 to run tests against the real API")
    if not os.getenv("MIXCLOUD_TOKEN"):
        pytest.fail("MIXCLOUD_LIVE=1 but MIXCLOUD_TOKEN is not set")


@pytest.mark.live
def test_token_is_valid():
    require_live()
    result = oauth.check_token()
    assert result["valid"] is True, result


@pytest.mark.live
def test_get_tag_athens():
    require_live()
    assert read.get_tag("funk")["name"]


@pytest.mark.live
def test_list_items_sends_offset():
    require_live()
    shows = read.browse("popular", limit=3, offset=0)
    assert len(shows) <= 3


@pytest.mark.live
def test_public_api_reachable():
    require_live()
    response = client.request("GET", "/spartacus/")
    assert response.status_code == 200

"""Key normalisation, trimming, and the rules that keep the token out of output."""

import httpx
import pytest
import respx

from mixcloud_mcp_server import client, state
from mixcloud_mcp_server.errors import MixcloudError


class TestNormalizeKey:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("spartacus", "/spartacus/"),
            ("/spartacus/", "/spartacus/"),
            ("  /spartacus/party-time/  ", "/spartacus/party-time/"),
            ("https://www.mixcloud.com/spartacus/party-time/", "/spartacus/party-time/"),
            ("https://api.mixcloud.com/spartacus/", "/spartacus/"),
        ],
    )
    def test_accepts_keys_and_mixcloud_urls(self, given: str, expected: str):
        assert client.normalize_key(given) == expected

    @pytest.mark.parametrize(
        "given",
        [
            "https://evil.example.com/steal/",
            "//evil.example.com/steal/",
            "/spartacus/../../etc/passwd",
            "/spartacus/?limit=1",
            "/spartacus/#frag",
            "spartacus\\party-time",
            "file:///etc/passwd",
        ],
    )
    def test_rejects_anything_else(self, given: str):
        """A key must never become a way to reach another host or a local path."""
        with pytest.raises(ValueError):
            client.normalize_key(given)


class TestTrim:
    def test_keeps_only_the_context_budget_fields(self):
        items = [
            {
                "key": "/a/b/",
                "name": "B",
                "url": "https://www.mixcloud.com/a/b/",
                "username": "a",
                "created_time": "2020-01-01T00:00:00Z",
                "play_count": 5,
                "favorite_count": 2,
                "audio_length": 3600,
                "tags": [{"name": "funk"}],
                "description": "a long description nobody needs in a list",
                "images": {"large": "https://images.mixcloud.com/..."},
            }
        ]
        assert client.trim(items) == [
            {
                "key": "/a/b/",
                "name": "B",
                "url": "https://www.mixcloud.com/a/b/",
                "username": "a",
                "created_time": "2020-01-01T00:00:00Z",
                "play_count": 5,
                "favorite_count": 2,
                "audio_length": 3600,
                "tags": [{"name": "funk"}],
            }
        ]

    def test_tolerates_absent_fields(self):
        assert client.trim([{"key": "/a/b/"}, {}]) == [{"key": "/a/b/"}, {}]


class TestRequest:
    @respx.mock
    def test_auth_sends_the_token_as_a_query_parameter(self, fake_token: str):
        route = respx.get("https://api.mixcloud.com/me/").mock(
            return_value=httpx.Response(200, json={"username": "tester"})
        )
        client.request("GET", "me", auth=True)
        assert route.calls.last.request.url.params["access_token"] == fake_token

    @respx.mock
    def test_redirects_are_not_followed_for_authenticated_calls(self, fake_token: str):
        """Otherwise the token would be replayed to whatever host is named."""
        origin = respx.get("https://api.mixcloud.com/me/").mock(
            return_value=httpx.Response(302, headers={"Location": "https://evil.example.com/"})
        )
        redirect_target = respx.get("https://evil.example.com/").mock(
            return_value=httpx.Response(200, json={})
        )
        response = client.request("GET", "me", auth=True)
        assert response.status_code == 302
        assert origin.call_count == 1
        assert not redirect_target.called

    @respx.mock
    def test_redirects_are_followed_for_public_calls(self):
        respx.get("https://api.mixcloud.com/new/").mock(
            return_value=httpx.Response(302, headers={"Location": "https://api.mixcloud.com/new2/"})
        )
        respx.get("https://api.mixcloud.com/new2/").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        assert client.list_items("new", 5, 0) == []

    @respx.mock
    def test_auth_without_a_token_never_reaches_the_network(self):
        with pytest.raises(MixcloudError, match="auth_url"):
            client.request("GET", "me", auth=True)

    @respx.mock
    def test_none_params_are_dropped(self):
        route = respx.get("https://api.mixcloud.com/me/").mock(
            return_value=httpx.Response(200, json={})
        )
        client.request("GET", "me", params={"metadata": None, "limit": 5})
        assert "metadata" not in route.calls.last.request.url.params

    @respx.mock
    def test_error_message_never_contains_the_token(self, fake_token: str):
        respx.get("https://api.mixcloud.com/me/").mock(
            return_value=httpx.Response(
                401,
                json={"error": {"type": "auth", "message": "invalid access token"}},
            )
        )
        with pytest.raises(MixcloudError) as caught:
            client.request("GET", "me", auth=True)
        message = str(caught.value)
        assert fake_token not in message
        assert "access_token" not in message
        assert "auth_url" in message  # it tells the model how to recover

    @respx.mock
    def test_error_message_never_contains_the_url(self):
        respx.get("https://api.mixcloud.com/spartacus/").mock(
            return_value=httpx.Response(500, text="boom")
        )
        with pytest.raises(MixcloudError) as caught:
            client.request("GET", "spartacus")
        assert "api.mixcloud.com" not in str(caught.value)

    @respx.mock
    def test_retry_after_is_surfaced(self):
        respx.get("https://api.mixcloud.com/spartacus/").mock(
            return_value=httpx.Response(
                429, json={"error": {"type": "rate", "message": "slow down", "retry_after": 30}}
            )
        )
        with pytest.raises(MixcloudError, match="retry after 30s"):
            client.request("GET", "spartacus")

    @respx.mock
    def test_network_failures_become_mixcloud_errors(self):
        respx.get("https://api.mixcloud.com/spartacus/").mock(
            side_effect=httpx.ConnectError("no route")
        )
        with pytest.raises(MixcloudError, match="Network error: ConnectError"):
            client.request("GET", "spartacus")


class TestListItems:
    @respx.mock
    def test_offset_is_always_sent(self):
        """Without offset the API pages by date, which returns the wrong shows."""
        route = respx.get("https://api.mixcloud.com/popular/").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        client.list_items("popular", 10, 0)
        params = route.calls.last.request.url.params
        assert params["limit"] == "10"
        assert params["offset"] == "0"

    @respx.mock
    def test_since_and_until_pass_through(self):
        route = respx.get("https://api.mixcloud.com/popular/").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        client.list_items(
            "popular", 5, 10, since="2020-01-01 00:00:00", until="2021-01-01 00:00:00"
        )
        params = route.calls.last.request.url.params
        assert params["since"] == "2020-01-01 00:00:00"
        assert params["until"] == "2021-01-01 00:00:00"


class TestAsJson:
    def test_non_json_becomes_a_short_excerpt(self):
        response = httpx.Response(200, text="<html>" + "x" * 1000)
        result = client.as_json(response)
        assert result["status"] == 200
        assert len(result["body"]) == 500


class TestTokenHelpers:
    def test_mask_hides_everything_but_the_last_four(self):
        assert state.mask("supersecrettoken1234") == "...1234"

    def test_require_token_explains_how_to_authorise(self):
        with pytest.raises(MixcloudError, match="exchange_code"):
            state.require_token()

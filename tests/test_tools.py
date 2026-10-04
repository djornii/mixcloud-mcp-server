"""Tools as the model sees them: names, arguments, and the requests they make."""

import asyncio
import re

import httpx
import pytest
import respx

from mixcloud_mcp_server.errors import MixcloudError
from mixcloud_mcp_server.server import mcp
from mixcloud_mcp_server.tools import oauth, read, upload, write

BASE = "https://api.mixcloud.com"


def tool_names() -> set[str]:
    return {tool.name for tool in asyncio.run(mcp.list_tools())}


class TestToolSurface:
    def test_every_tool_is_registered(self):
        """Tool names are the public contract: users' prompts and skills call them."""
        assert tool_names() == {
            "search",
            "get_object",
            "get_show",
            "get_user",
            "get_tag",
            "list_connection",
            "user_shows",
            "browse",
            "genre_shows",
            "embed_html",
            "oembed",
            "me",
            "follow_user",
            "favorite_show",
            "repost_show",
            "listen_later",
            "upload_show",
            "edit_show",
            "auth_url",
            "exchange_code",
            "check_token",
            "clear_token",
        }

    def test_tools_stay_plain_callable_functions(self):
        """FastMCP's decorator returns the function, which user_shows relies on."""
        assert read.user_shows.__name__ == "user_shows"
        assert callable(read.user_shows)

    def test_every_tool_has_a_description(self):
        for tool in asyncio.run(mcp.list_tools()):
            assert tool.description, tool.name


class TestReadTools:
    @respx.mock
    def test_search_trims_results(self):
        respx.get(f"{BASE}/search/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "key": "/a/b/",
                            "name": "B",
                            "username": "a",
                            "description": "dropped",
                        }
                    ]
                },
            )
        )
        assert read.search("funk") == [{"key": "/a/b/", "name": "B", "username": "a"}]

    @respx.mock
    def test_user_shows_goes_through_the_cloudcasts_connection(self):
        route = respx.get(f"{BASE}/spartacus/cloudcasts/").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        read.user_shows("/spartacus/")
        assert route.called

    @respx.mock
    def test_list_connection_accepts_a_full_url_as_key(self):
        route = respx.get(f"{BASE}/spartacus/followers/").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        read.list_connection("https://www.mixcloud.com/spartacus/", "followers")
        assert route.called

    @respx.mock
    def test_get_tag_combines_tag_and_city(self):
        route = respx.get(f"{BASE}/genres/funk+city:athens/").mock(
            return_value=httpx.Response(200, json={})
        )
        read.get_tag("funk", "athens")
        assert route.called

    def test_get_tag_needs_something(self):
        with pytest.raises(ValueError, match="tag and/or city"):
            read.get_tag()

    @pytest.mark.parametrize(
        ("list_name", "path"),
        [("popular", "/popular/"), ("hot", "/popular/hot/"), ("new", "/new/")],
    )
    @respx.mock
    def test_browse_paths(self, list_name: str, path: str):
        route = respx.get(BASE + path).mock(return_value=httpx.Response(200, json={"data": []}))
        read.browse(list_name)
        assert route.called

    @respx.mock
    def test_genre_shows_resolves_the_list_from_the_tag_metadata(self):
        respx.get(f"{BASE}/genres/funk/").mock(
            return_value=httpx.Response(
                200,
                json={"metadata": {"connections": {"popular": f"{BASE}/genres/funk/popular/"}}},
            )
        )
        route = respx.get(f"{BASE}/genres/funk/popular/").mock(
            return_value=httpx.Response(200, json={"data": [{"key": "/a/b/"}]})
        )
        assert read.genre_shows("funk") == [{"key": "/a/b/"}]
        assert route.called

    @respx.mock
    def test_genre_shows_rejects_an_unknown_list_name(self):
        respx.get(f"{BASE}/genres/funk/").mock(
            return_value=httpx.Response(
                200, json={"metadata": {"connections": {"popular": f"{BASE}/genres/funk/popular/"}}}
            )
        )
        with pytest.raises(MixcloudError, match="Tag has no 'charts' list"):
            read.genre_shows("funk", "charts")

    @respx.mock
    def test_genre_shows_refuses_a_connection_url_off_the_api_host(self):
        """The connection URL comes from the API body: do not follow it anywhere else."""
        respx.get(f"{BASE}/genres/funk/").mock(
            return_value=httpx.Response(
                200,
                json={"metadata": {"connections": {"popular": "https://evil.example.com/x"}}},
            )
        )
        with pytest.raises(MixcloudError, match="Unexpected connection URL"):
            read.genre_shows("funk")

    @respx.mock
    def test_embed_html_returns_raw_text(self):
        respx.get(f"{BASE}/spartacus/party-time/embed-html/").mock(
            return_value=httpx.Response(200, text="<iframe></iframe>")
        )
        assert read.embed_html("/spartacus/party-time/") == "<iframe></iframe>"

    def test_embed_html_rejects_a_bad_colour(self):
        with pytest.raises(ValueError, match="6-digit hex"):
            read.embed_html("/spartacus/party-time/", color="#ff0000")

    def test_oembed_rejects_a_foreign_url(self):
        with pytest.raises(ValueError, match=r"must start with https://www\.mixcloud\.com/"):
            read.oembed("https://evil.example.com/a/b/")


class TestWriteTools:
    @respx.mock
    def test_me_sends_the_token(self, fake_token: str):
        route = respx.get(f"{BASE}/me/").mock(
            return_value=httpx.Response(200, json={"username": "tester"})
        )
        assert write.me()["username"] == "tester"
        assert route.calls.last.request.url.params["access_token"] == fake_token

    @respx.mock
    def test_me_without_a_token_never_reaches_the_network(self):
        with pytest.raises(MixcloudError, match="auth_url"):
            write.me()

    @respx.mock
    @pytest.mark.parametrize(
        ("tool", "action"),
        [
            (write.follow_user, "follow"),
            (write.favorite_show, "favorite"),
            (write.repost_show, "repost"),
            (write.listen_later, "listen-later"),
        ],
    )
    def test_undo_uses_delete(self, fake_token: str, tool, action: str):
        route = respx.delete(f"{BASE}/spartacus/party-time/{action}/").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        tool("/spartacus/party-time/", undo=True)
        assert route.called

    @respx.mock
    def test_redo_uses_post(self, fake_token: str):
        route = respx.post(f"{BASE}/spartacus/follow/").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        write.follow_user("/spartacus/")
        assert route.called

    @respx.mock
    def test_edit_show_targets_the_upload_edit_path(self, fake_token: str):
        route = respx.post(f"{BASE}/upload/me-user/my-upload/edit/").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        upload.edit_show("/me-user/my-upload/", name="New name")
        assert route.called


class TestOauthTools:
    def test_auth_url_needs_a_client_id(self):
        with pytest.raises(MixcloudError, match="MIXCLOUD_CLIENT_ID"):
            oauth.auth_url()

    def test_auth_url_points_at_mixcloud(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MIXCLOUD_CLIENT_ID", "client-123")
        url = oauth.auth_url()["url"]
        assert url.startswith("https://www.mixcloud.com/oauth/authorize?")
        assert "client_id=client-123" in url

    def test_auth_url_includes_the_redirect_uri_when_given(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MIXCLOUD_CLIENT_ID", "client-123")
        url = oauth.auth_url("https://example.com/cb")["url"]
        assert "redirect_uri=https%3A%2F%2Fexample.com%2Fcb" in url

    def test_exchange_code_needs_both_credentials(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MIXCLOUD_CLIENT_ID", "client-123")
        with pytest.raises(MixcloudError, match="CLIENT_SECRET"):
            oauth.exchange_code("code")

    @respx.mock
    def test_exchange_code_stores_the_token_and_never_returns_it(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        secret = "shhh"
        token = "1tok-real-looking-value-4321"
        monkeypatch.setenv("MIXCLOUD_CLIENT_ID", "client-123")
        monkeypatch.setenv("MIXCLOUD_CLIENT_SECRET", secret)
        respx.get("https://www.mixcloud.com/oauth/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": token})
        )
        respx.get(f"{BASE}/me/").mock(
            return_value=httpx.Response(200, json={"username": "tester", "name": "Tester"})
        )
        result = oauth.exchange_code("the-code")

        assert token not in repr(result)
        assert secret not in repr(result)
        assert result["token_preview"] == "...4321"
        assert result["account"]["username"] == "tester"
        assert result["saved_to_env_file"] is True
        from dotenv import dotenv_values

        assert dotenv_values(oauth.config.env_file())["MIXCLOUD_TOKEN"] == token

    @respx.mock
    def test_exchange_code_accepts_a_bare_query_string_response(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Mixcloud has answered this endpoint with both shapes."""
        token = "1tok-querystring-value-7777"
        monkeypatch.setenv("MIXCLOUD_CLIENT_ID", "client-123")
        monkeypatch.setenv("MIXCLOUD_CLIENT_SECRET", "shhh")
        respx.get("https://www.mixcloud.com/oauth/access_token").mock(
            return_value=httpx.Response(200, text=f"access_token={token}")
        )
        respx.get(f"{BASE}/me/").mock(return_value=httpx.Response(200, json={"username": "tester"}))
        assert oauth.exchange_code("the-code")["token_preview"] == "...7777"

    @respx.mock
    def test_exchange_code_reports_a_reused_code(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MIXCLOUD_CLIENT_ID", "client-123")
        monkeypatch.setenv("MIXCLOUD_CLIENT_SECRET", "shhh")
        respx.get("https://www.mixcloud.com/oauth/access_token").mock(
            return_value=httpx.Response(200, json={"error": "expired"})
        )
        with pytest.raises(MixcloudError, match="No access_token"):
            oauth.exchange_code("the-code")

    def test_check_token_without_a_token(self):
        assert oauth.check_token() == {"valid": False, "reason": "no token set"}

    @respx.mock
    def test_check_token_reports_an_invalid_token(self, fake_token: str):
        respx.get(f"{BASE}/me/").mock(
            return_value=httpx.Response(
                401, json={"error": {"type": "auth", "message": "invalid access token"}}
            )
        )
        result = oauth.check_token()
        assert result["valid"] is False
        assert fake_token not in repr(result)

    def test_clear_token_keeps_the_env_file_by_default(self, fake_token: str):
        result = oauth.clear_token()
        assert result == {"cleared_in_memory": True, "removed_from_env_file": False}

    def test_clear_token_can_remove_it_from_the_env_file(self, fake_token: str):
        oauth.state.write_token(fake_token)
        from dotenv import dotenv_values

        result = oauth.clear_token(remove_from_env_file=True)
        assert result["removed_from_env_file"] is True
        assert "MIXCLOUD_TOKEN" not in dict(dotenv_values(oauth.config.env_file()))


class TestNoStdoutWrites:
    """stdout is the JSON-RPC channel. A stray print corrupts the protocol."""

    def test_no_print_in_the_package(self):
        """Any print without the CLI escape hatch corrupts the JSON-RPC stream."""
        import pathlib

        import mixcloud_mcp_server

        package = pathlib.Path(mixcloud_mcp_server.__file__).parent
        offenders = [
            f"{path.relative_to(package)}:{number}"
            for path in package.rglob("*.py")
            for number, line in enumerate(path.read_text().splitlines(), 1)
            if re.search(r"^\s*print\(", line) and path.name != "server.py"
        ]
        assert offenders == []


def test_live_marker_is_registered(pytestconfig: pytest.Config):
    """MIXCLOUD_LIVE gates the live suite; the marker must exist to be selected."""
    assert any("live" in marker for marker in pytestconfig.getini("markers"))

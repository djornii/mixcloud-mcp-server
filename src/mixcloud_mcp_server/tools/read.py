"""Tools that work without an access token."""

import re
from typing import Any, Literal

from .. import client
from ..errors import MixcloudError, as_tool_error


def search(
    query: str,
    type: Literal["cloudcast", "user", "tag"] = "cloudcast",
    limit: int = 10,
    offset: int = 0,
) -> list[dict]:
    """Search Mixcloud. type: 'cloudcast' (shows), 'user' or 'tag'."""
    response = client.request(
        "GET",
        "search",
        params={"q": query, "type": type, "limit": limit, "offset": offset},
    )
    return client.trim(response.json().get("data", []))


def get_object(key: str, metadata: bool = False, authenticated: bool = False) -> Any:
    """Fetch any object by key or Mixcloud URL: show '/spartacus/party-time/',
    user '/spartacus/', tag '/genres/funk/', city '/genres/city:athens/'.
    metadata=True adds the list of available connections. authenticated=True
    sends the token so objects gain extra fields (e.g. 'following')."""
    response = client.request(
        "GET", key, params={"metadata": 1 if metadata else None}, auth=authenticated
    )
    return client.as_json(response)


def get_show(key: str) -> dict:
    """Get a show by key, e.g. '/spartacus/party-time/'."""
    data = client.request("GET", key).json()
    return {
        field: data.get(field)
        for field in (
            "key",
            "name",
            "url",
            "description",
            "created_time",
            "audio_length",
            "play_count",
            "favorite_count",
            "tags",
            "user",
        )
    }


def get_user(key: str) -> Any:
    """Get a user profile by key, e.g. '/spartacus/'."""
    return client.as_json(client.request("GET", key))


def get_tag(tag: str | None = None, city: str | None = None) -> Any:
    """Get a tag/genre ('funk'), a city ('athens'), or both ('funk' + 'athens')."""
    parts = [p for p in (tag, f"city:{city}" if city else None) if p]
    if not parts:
        raise ValueError("Provide tag and/or city")
    return client.as_json(client.request("GET", "genres/" + "+".join(parts)))


def list_connection(
    key: str,
    connection: str,
    limit: int = 20,
    offset: int = 0,
    since: str | None = None,
    until: str | None = None,
    authenticated: bool = False,
) -> list[dict]:
    """List a connection of an object, e.g. key='/spartacus/' with connection
    'followers' | 'following' | 'favorites' | 'cloudcasts' | 'listens'.
    Use key='/me/' with authenticated=True for the token owner's own lists.
    since/until: Unix timestamp or 'YYYY-MM-DD HH:MM:SS' (UTC), for dated lists."""
    return client.list_items(
        client.normalize_key(key) + connection.strip("/"),
        limit,
        offset,
        since=since,
        until=until,
        auth=authenticated,
    )


def user_shows(
    key: str,
    limit: int = 10,
    offset: int = 0,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """List a user's shows. key: '/spartacus/'."""
    return list_connection(key, "cloudcasts", limit, offset, since, until)


def browse(
    list_name: Literal["popular", "hot", "new"] = "popular",
    limit: int = 10,
    offset: int = 0,
) -> list[dict]:
    """Site-wide lists: popular, hot or new shows."""
    path = {"popular": "popular", "hot": "popular/hot", "new": "new"}[list_name]
    return client.list_items(path, limit, offset)


def genre_shows(
    tag: str, list_name: str = "popular", limit: int = 10, offset: int = 0
) -> list[dict]:
    """Shows of a tag/genre. Looks the list up in the tag's own connections
    (metadata=1), so list_name must be one the tag offers; the error lists them."""
    response = client.request("GET", f"genres/{tag}", params={"metadata": 1})
    connections = response.json().get("metadata", {}).get("connections", {})
    url = connections.get(list_name)
    if not url:
        raise MixcloudError(f"Tag has no '{list_name}' list. Available: {sorted(connections)}")
    if not url.startswith(client.BASE + "/"):
        raise MixcloudError("Unexpected connection URL")
    return client.list_items(None, limit, offset, url=url)


def embed_html(
    key: str,
    width: int | None = None,
    height: int | None = None,
    color: str | None = None,
) -> str:
    """Embed code (HTML) for a show's player widget. color: 6-digit hex, no '#'."""
    if color is not None and not re.fullmatch(r"[0-9a-fA-F]{6}", color):
        raise ValueError("color must be a 6-digit hex without '#'")
    response = client.request(
        "GET",
        client.normalize_key(key) + "embed-html",
        params={"width": width, "height": height, "color": color},
    )
    return response.text


def oembed(url: str) -> Any:
    """oEmbed data for a Mixcloud show URL (https://www.mixcloud.com/...)."""
    if not re.match(r"^https://www\.mixcloud\.com/", url):
        raise ValueError("url must start with https://www.mixcloud.com/")
    return client.as_json(
        client.request("GET", url=client.OEMBED, params={"url": url, "format": "json"})
    )


def register(mcp) -> None:
    for tool in (
        search,
        get_object,
        get_show,
        get_user,
        get_tag,
        list_connection,
        user_shows,
        browse,
        genre_shows,
        embed_html,
        oembed,
    ):
        mcp.tool()(as_tool_error(tool))

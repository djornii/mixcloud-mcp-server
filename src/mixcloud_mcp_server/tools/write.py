"""Tools that act as the token owner."""

from typing import Any

from .. import client
from ..errors import as_tool_error


def me(metadata: bool = False) -> Any:
    """The authorized user's own profile (/me/)."""
    return client.as_json(
        client.request("GET", "me", params={"metadata": 1 if metadata else None}, auth=True)
    )


def _act(key: str, action: str, undo: bool) -> Any:
    return client.as_json(
        client.request("DELETE" if undo else "POST", client.normalize_key(key) + action, auth=True)
    )


def follow_user(key: str, undo: bool = False) -> Any:
    """Follow a user ('/spartacus/'); undo=True unfollows."""
    return _act(key, "follow", undo)


def favorite_show(key: str, undo: bool = False) -> Any:
    """Favorite a show ('/spartacus/party-time/'); undo=True removes it from favorites."""
    return _act(key, "favorite", undo)


def repost_show(key: str, undo: bool = False) -> Any:
    """Repost a show; undo=True removes the repost."""
    return _act(key, "repost", undo)


def listen_later(key: str, undo: bool = False) -> Any:
    """Add a show to Listen Later; undo=True removes it."""
    return _act(key, "listen-later", undo)


def register(mcp) -> None:
    for tool in (me, follow_user, favorite_show, repost_show, listen_later):
        mcp.tool()(as_tool_error(tool))

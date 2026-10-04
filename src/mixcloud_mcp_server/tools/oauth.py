"""OAuth and token tools.

The client secret is read from the environment and never returned. The token that
comes back from Mixcloud is stored in :mod:`mixcloud_mcp_server.state` and reported only as
a masked preview, so a model cannot exfiltrate it by asking a follow-up question.
"""

from urllib.parse import parse_qs, urlencode

from .. import client, config, state
from ..errors import MixcloudError, as_tool_error


def auth_url(redirect_uri: str | None = None) -> dict:
    """Step 1 of OAuth: URL the user must open in a browser to allow access.
    Without redirect_uri, Mixcloud shows the code on screen; with it, the code
    arrives as ?code=... on that URL. Then call exchange_code(code)."""
    client_id = config.env("MIXCLOUD_CLIENT_ID")
    if not client_id:
        raise MixcloudError("MIXCLOUD_CLIENT_ID is not set")
    query = {"client_id": client_id}
    if redirect_uri:
        query["redirect_uri"] = redirect_uri
    return {
        "url": f"{client.WWW}/oauth/authorize?{urlencode(query)}",
        "next": "Open the URL, allow access, then call exchange_code with the code. "
        "Pass the same redirect_uri there if you used one here.",
    }


def exchange_code(code: str, redirect_uri: str | None = None) -> dict:
    """Step 2 of OAuth: exchange the code for an access token. The token is
    kept in this server (and saved to the env file); it is not shown to you."""
    client_id = config.env("MIXCLOUD_CLIENT_ID")
    secret = config.env("MIXCLOUD_CLIENT_SECRET")
    if not client_id or not secret:
        raise MixcloudError("MIXCLOUD_CLIENT_ID / MIXCLOUD_CLIENT_SECRET are not set")
    response = client.request(
        "GET",
        url=f"{client.WWW}/oauth/access_token",
        params={
            "client_id": client_id,
            "client_secret": secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    # Mixcloud has returned both JSON and a bare query string over the years.
    try:
        body = response.json()
        token = body.get("access_token") if isinstance(body, dict) else None
    except ValueError:
        token = parse_qs(response.text.strip()).get("access_token", [None])[0]
    if not token:
        raise MixcloudError("No access_token in the response (code expired or reused?)")
    state.set_token(token, persist=False)
    return {
        "ok": True,
        "token_preview": state.mask(token),
        "saved_to_env_file": state.write_token(token),
        "account": check_token(),
    }


def check_token() -> dict:
    """Check that the current token works (calls /me/)."""
    if not state.token():
        return {"valid": False, "reason": "no token set"}
    try:
        data = client.request("GET", "me", auth=True).json()
    except MixcloudError as exc:
        return {"valid": False, "reason": str(exc)}
    return {
        "valid": True,
        "username": data.get("username"),
        "name": data.get("name"),
        "token_preview": state.mask(state.token() or ""),
    }


def clear_token(remove_from_env_file: bool = False) -> dict:
    """Forget the token in this server (and optionally delete it from the env
    file). This does not revoke it on Mixcloud: the API docs describe no revoke
    endpoint, the user revokes access on Mixcloud's side."""
    state.forget()
    removed = state.write_token(None) if remove_from_env_file else False
    return {"cleared_in_memory": True, "removed_from_env_file": removed}


def register(mcp) -> None:
    for tool in (auth_url, exchange_code, check_token, clear_token):
        mcp.tool()(as_tool_error(tool))

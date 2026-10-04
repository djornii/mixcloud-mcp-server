"""Every HTTP request to Mixcloud goes through this module.

Two rules hold here and are the reason the module exists:

* The access token is a query parameter, so a URL must never reach a log record or
  an exception message. That is what :func:`raise_api_error` is careful about.
* Redirects are never followed for authenticated calls, or the token would be
  replayed to whatever host the redirect names.
"""

import re
from typing import Any, NoReturn

import httpx

from . import config, state
from .errors import MixcloudError

BASE = "https://api.mixcloud.com"
WWW = "https://www.mixcloud.com"
OEMBED = "https://app.mixcloud.com/oembed/"

DEFAULT_TIMEOUT = 15.0
UPLOAD_TIMEOUT = httpx.Timeout(60.0, write=None, read=900.0)

config.quiet_http_loggers()


def normalize_key(key: str) -> str:
    """Turn a key or a Mixcloud URL into ``/a/b/``. Rejects anything else.

    Accepts a full URL only for the two Mixcloud hosts; every other scheme or
    host is an error, so a key can never be used to reach a third-party server.
    """
    cleaned = re.sub(r"^https?://(www|api)\.mixcloud\.com", "", key.strip())
    # "//" catches protocol-relative URLs, which would otherwise sneak through as a path.
    if any(c in cleaned for c in "?#\\") or "//" in cleaned or ".." in cleaned:
        raise ValueError(f"Invalid key: {key!r}")
    return "/" + cleaned.strip("/") + "/"


def raise_api_error(response: httpx.Response) -> NoReturn:
    """Turn a Mixcloud error body into a MixcloudError, without the URL."""
    try:
        error = response.json().get("error", {})
    except ValueError:
        error = {}
    message = error.get("message") or f"HTTP {response.status_code}"
    if error.get("retry_after"):
        message += f" (retry after {error['retry_after']}s)"
    if "invalid access token" in message.lower():
        message += " Token is revoked or invalid: run auth_url + exchange_code again."
    # Deliberately no URL here: it may carry the access token.
    raise MixcloudError(
        f"Mixcloud API error {response.status_code} {error.get('type', '')}: {message}"
    )


def request(
    method: str,
    path: str | None = None,
    *,
    params: dict[str, Any] | None = None,
    auth: bool = False,
    files: list | None = None,
    timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
    url: str | None = None,
) -> httpx.Response:
    """Call Mixcloud and raise MixcloudError on anything 4xx or 5xx."""
    query = {k: v for k, v in (params or {}).items() if v is not None}
    if auth:
        query["access_token"] = state.require_token()
    target = url or BASE + normalize_key(path or "")
    try:
        response = httpx.request(
            method,
            target,
            params=query,
            files=files,
            timeout=timeout,
            follow_redirects=not auth,
        )
    except httpx.HTTPError as exc:
        raise MixcloudError(f"Network error: {type(exc).__name__}") from None
    if response.status_code >= 400:
        raise_api_error(response)
    return response


def as_json(response: httpx.Response) -> Any:
    """Decode a JSON body, or hand back a short excerpt of a non-JSON one."""
    try:
        return response.json()
    except ValueError:
        return {"status": response.status_code, "body": response.text[:500]}


# Fields worth showing a model. Everything else costs context and is ignored.
TRIM_FIELDS = (
    "key",
    "name",
    "url",
    "username",
    "created_time",
    "play_count",
    "favorite_count",
    "audio_length",
    "tags",
)


def trim(items: list[dict]) -> list[dict]:
    return [{k: item[k] for k in TRIM_FIELDS if k in item} for item in items]


def list_items(
    path: str | None,
    limit: int,
    offset: int,
    *,
    since: str | int | None = None,
    until: str | int | None = None,
    auth: bool = False,
    url: str | None = None,
) -> list[dict]:
    """Fetch one page of a list connection.

    ``offset`` is always sent: without it the API pages by date, which silently
    returns the wrong shows.
    """
    response = request(
        "GET",
        path,
        params={"limit": limit, "offset": offset, "since": since, "until": until},
        auth=auth,
        url=url,
    )
    return trim(response.json().get("data", []))

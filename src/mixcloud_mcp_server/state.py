"""The access token: in memory, and in the env file on disk.

The token is never returned to the model. Tools that need to report on it get
:func:`mask`, and the OAuth client secret is not stored here at all -- it is read
from the environment by ``tools.oauth`` and never leaves the process.
"""

import os

from dotenv import set_key, unset_key

from . import config
from .errors import MixcloudError

_token: str | None = None
_loaded = False


def token() -> str | None:
    """The current token, read from the environment on first use."""
    global _token, _loaded
    if not _loaded:
        _loaded = True
        _token = config.env("MIXCLOUD_TOKEN") or None
    return _token


def set_token(value: str | None, *, persist: bool = True) -> None:
    """Adopt a token in this process, and by default in the env file."""
    global _token, _loaded
    _token = value
    _loaded = True
    if value:
        os.environ["MIXCLOUD_TOKEN"] = value
    else:
        os.environ.pop("MIXCLOUD_TOKEN", None)
    if persist:
        write_token(value)


def require_token() -> str:
    value = token()
    if not value:
        raise MixcloudError(
            "No access token. Run auth_url, authorize in the browser, then exchange_code(code)."
        )
    return value


def forget() -> None:
    """Drop the token from this process. Does not touch the env file."""
    set_token(None, persist=False)


def mask(value: str) -> str:
    """Enough to recognise a token in a log line, not enough to use it."""
    return "..." + value[-4:]


def write_token(value: str | None) -> bool:
    """Persist (or remove) the token in the env file, mode 0600."""
    path = config.env_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600, exist_ok=True)
        if value:
            set_key(str(path), "MIXCLOUD_TOKEN", value)
        else:
            unset_key(str(path), "MIXCLOUD_TOKEN")
        os.chmod(path, 0o600)
        return True
    except Exception:
        # A read-only or otherwise unwritable env file must not break the server:
        # the token still works for this session.
        return False

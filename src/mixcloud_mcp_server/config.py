"""Environment variables and filesystem paths.

Nothing in this module runs at import time. ``main()`` calls :func:`load` before
any tool can reach the environment, and every other module reads variables through
:func:`env` so tests can just monkeypatch ``os.environ``.
"""

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

APP_NAME = "mixcloud-mcp-server"


def _xdg(var: str, fallback: str) -> Path:
    """An XDG base directory, falling back to the usual dotfile in $HOME."""
    return Path(os.getenv(var) or Path.home() / fallback).expanduser()


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value else default


def env_file() -> Path:
    """File the access token is persisted to, and loaded from at startup."""
    override = env("MIXCLOUD_ENV_FILE")
    if override:
        return Path(override).expanduser()
    return _xdg("XDG_CONFIG_HOME", ".config") / APP_NAME / ".env"


def upload_dir() -> Path:
    """The only directory uploads are allowed to read files from."""
    override = env("MIXCLOUD_UPLOAD_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (_xdg("XDG_DATA_HOME", ".local/share") / APP_NAME / "uploads").resolve()


def ensure_upload_dir() -> Path:
    directory = upload_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def load() -> None:
    """Read the env file, then quiet the HTTP loggers. Idempotent.

    ``load_dotenv`` does not override variables already present in the real
    environment, so a value exported by the MCP client config wins over the file.
    """
    load_dotenv(env_file())
    quiet_http_loggers()


def quiet_http_loggers() -> None:
    """Keep request URLs out of the logs.

    The access token travels as a query parameter, and httpx logs full URLs at
    INFO. A client that configures a root handler at INFO would otherwise leak it.
    """
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def describe() -> dict[str, Any]:
    """Resolved paths and which credentials exist. Never returns a secret."""
    return {
        "env_file": str(env_file()),
        "env_file_exists": env_file().is_file(),
        "upload_dir": str(upload_dir()),
        "upload_dir_exists": upload_dir().is_dir(),
        "has_token": bool(env("MIXCLOUD_TOKEN")),
        "has_client_id": bool(env("MIXCLOUD_CLIENT_ID")),
        "has_client_secret": bool(env("MIXCLOUD_CLIENT_SECRET")),
    }

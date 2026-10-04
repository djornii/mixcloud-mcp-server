"""Test fixtures.

Two things must be true before any test runs: the process must not see the
developer's real token, and no test may reach the network. The first is done here
at import time because the env file is read lazily but ``os.environ`` is not.
"""

import os
from pathlib import Path

import pytest

# Set before mixcloud_mcp_server is imported anywhere: a stray MIXCLOUD_TOKEN in the
# developer's shell must not make an authenticated test pass by accident.
os.environ.pop("MIXCLOUD_TOKEN", None)
os.environ.pop("MIXCLOUD_CLIENT_ID", None)
os.environ.pop("MIXCLOUD_CLIENT_SECRET", None)

from mixcloud_mcp_server import state


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the env file and upload dir at tmp_path, and reset module state.

    MIXCLOUD_TOKEN is cleared too: a test that calls config.load() writes into the
    real environment, and load_dotenv does not override what is already there.
    """
    env_file = tmp_path / "config" / ".env"
    uploads = tmp_path / "uploads"
    monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(env_file))
    monkeypatch.setenv("MIXCLOUD_UPLOAD_DIR", str(uploads))
    monkeypatch.delenv("MIXCLOUD_TOKEN", raising=False)

    monkeypatch.setattr(state, "_token", None)
    monkeypatch.setattr(state, "_loaded", True)
    yield
    monkeypatch.undo()


@pytest.fixture
def fake_token(monkeypatch: pytest.MonkeyPatch) -> str:
    token = "1tok-fake-value-9f3a"
    monkeypatch.setattr(state, "_token", token)
    monkeypatch.setattr(state, "_loaded", True)
    monkeypatch.setenv("MIXCLOUD_TOKEN", token)
    return token

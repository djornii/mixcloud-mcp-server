"""Token storage: in memory and in the env file."""

import os
import stat

from dotenv import dotenv_values

from mixcloud_mcp_server import config, state


def read_env(path) -> dict:
    """Parse the env file. set_key quotes values, so match text, not substrings."""
    return dict(dotenv_values(path))


def test_token_is_read_from_the_environment(monkeypatch, fake_token):
    monkeypatch.setattr(state, "_loaded", False)
    monkeypatch.setattr(state, "_token", None)
    assert state.token() == fake_token


def test_token_is_none_when_unset(monkeypatch):
    monkeypatch.setattr(state, "_loaded", False)
    monkeypatch.setattr(state, "_token", None)
    monkeypatch.delenv("MIXCLOUD_TOKEN", raising=False)
    assert state.token() is None


def test_set_token_mirrors_into_the_environment(monkeypatch, fake_token):
    new = "1tok-brand-new-5555"
    state.set_token(new, persist=False)
    assert state.token() == new
    assert os.environ["MIXCLOUD_TOKEN"] == new


def test_forget_drops_the_token(monkeypatch, fake_token):
    state.forget()
    assert state.token() is None
    assert "MIXCLOUD_TOKEN" not in os.environ


class TestWriteToken:
    def test_writes_the_token(self, monkeypatch, tmp_path):
        env_file = tmp_path / "config" / ".env"
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(env_file))
        assert state.write_token("1tok-written-9999") is True
        assert read_env(env_file)["MIXCLOUD_TOKEN"] == "1tok-written-9999"

    def test_file_is_owner_only(self, monkeypatch, tmp_path):
        env_file = tmp_path / "config" / ".env"
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(env_file))
        state.write_token("1tok-written-9999")
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600

    def test_tightens_permissions_on_an_existing_loose_file(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER=keep\n")
        env_file.chmod(0o644)
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(env_file))
        state.write_token("1tok-written-9999")
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600

    def test_preserves_other_keys(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MIXCLOUD_CLIENT_ID=client-123\n")
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(env_file))
        state.write_token("1tok-written-9999")
        values = read_env(env_file)
        assert values["MIXCLOUD_CLIENT_ID"] == "client-123"
        assert values["MIXCLOUD_TOKEN"] == "1tok-written-9999"

    def test_removes_the_key(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(env_file))
        state.write_token("1tok-written-9999")
        state.write_token(None)
        assert "MIXCLOUD_TOKEN" not in read_env(env_file)

    def test_unwritable_path_reports_false_instead_of_raising(
        self, monkeypatch, tmp_path, fake_token
    ):
        """A read-only env file must not take the server down mid-session."""
        unwritable = tmp_path / "readonly"
        unwritable.mkdir()
        unwritable.chmod(0o500)
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(unwritable / "sub" / ".env"))
        try:
            assert state.write_token("1tok-written-9999") is False
        finally:
            unwritable.chmod(0o700)

    def test_survives_a_round_trip_through_the_env_file(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(env_file))
        state.write_token("1tok-round-trip-1234")
        config.load()
        monkeypatch.setattr(state, "_loaded", False)
        monkeypatch.setattr(state, "_token", None)
        assert state.token() == "1tok-round-trip-1234"

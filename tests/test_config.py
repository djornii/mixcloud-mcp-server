"""Config: path resolution and env loading."""

import os
from pathlib import Path

from mixcloud_mcp_server import config


class TestEnvFile:
    def test_explicit_override_wins(self, monkeypatch, tmp_path: Path):
        target = tmp_path / "somewhere" / ".env"
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(target))
        assert config.env_file() == target

    def test_override_is_expanded(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("MIXCLOUD_ENV_FILE", raising=False)
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", "~/dot.env")
        assert config.env_file() == tmp_path / "dot.env"

    def test_default_uses_xdg_config_home(self, monkeypatch, tmp_path: Path):
        monkeypatch.delenv("MIXCLOUD_ENV_FILE", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        assert config.env_file() == tmp_path / "cfg" / "mixcloud-mcp-server" / ".env"

    def test_default_falls_back_to_home_dot_config(self, monkeypatch, tmp_path: Path):
        monkeypatch.delenv("MIXCLOUD_ENV_FILE", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        assert config.env_file() == tmp_path / ".config" / "mixcloud-mcp-server" / ".env"


class TestUploadDir:
    def test_explicit_override_is_resolved(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("MIXCLOUD_UPLOAD_DIR", str(tmp_path / "up"))
        assert config.upload_dir() == (tmp_path / "up").resolve()

    def test_default_uses_xdg_data_home(self, monkeypatch, tmp_path: Path):
        monkeypatch.delenv("MIXCLOUD_UPLOAD_DIR", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        assert (
            config.upload_dir() == (tmp_path / "data" / "mixcloud-mcp-server" / "uploads").resolve()
        )

    def test_ensure_creates_it(self, monkeypatch, tmp_path: Path):
        target = tmp_path / "deep" / "uploads"
        monkeypatch.setenv("MIXCLOUD_UPLOAD_DIR", str(target))
        assert config.ensure_upload_dir() == target.resolve()
        assert target.is_dir()


class TestLoad:
    def test_load_reads_the_env_file(self, monkeypatch, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("MIXCLOUD_TOKEN=from-file\n")
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(env_file))
        monkeypatch.delenv("MIXCLOUD_TOKEN", raising=False)
        config.load()
        assert os.environ["MIXCLOUD_TOKEN"] == "from-file"

    def test_real_environment_wins_over_the_file(self, monkeypatch, tmp_path: Path):
        """An MCP client that exports the variable in its config must not be overridden."""
        env_file = tmp_path / ".env"
        env_file.write_text("MIXCLOUD_TOKEN=from-file\n")
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(env_file))
        monkeypatch.setenv("MIXCLOUD_TOKEN", "from-environment")
        config.load()
        assert os.environ["MIXCLOUD_TOKEN"] == "from-environment"

    def test_missing_env_file_is_not_an_error(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(tmp_path / "nope" / ".env"))
        config.load()

    def test_quiet_http_loggers_pins_httpx_to_warning(self):
        import logging

        config.quiet_http_loggers()
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING


class TestDescribe:
    def test_reports_paths_without_secrets(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(tmp_path / ".env"))
        monkeypatch.setenv("MIXCLOUD_UPLOAD_DIR", str(tmp_path / "up"))
        monkeypatch.setenv("MIXCLOUD_TOKEN", "super-secret-token-value")
        monkeypatch.setenv("MIXCLOUD_CLIENT_ID", "client-123")
        described = config.describe()
        assert described["has_token"] is True
        assert described["has_client_id"] is True
        assert "super-secret-token-value" not in repr(described)
        assert "client-123" not in repr(described)

    def test_has_client_secret_never_leaks_it(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("MIXCLOUD_ENV_FILE", str(tmp_path / ".env"))
        monkeypatch.setenv("MIXCLOUD_CLIENT_SECRET", "the-secret")
        assert config.describe()["has_client_secret"] is True
        assert "the-secret" not in repr(config.describe())

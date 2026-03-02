from pathlib import Path

from trigr.config import find_config, load_config, server_url
from trigr.models import TrigrConfig, ServerConfig


class TestFindConfig:
    def test_found(self, tmp_path: Path, monkeypatch: object) -> None:
        toml = tmp_path / "trigr.toml"
        toml.write_text('[server]\nport = 9999\n')
        monkeypatch.setattr("trigr.config.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        assert find_config() == toml

    def test_not_found(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.config.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        assert find_config() is None


class TestLoadConfig:
    def test_defaults_when_missing(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.config.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        cfg = load_config()
        assert cfg.server.port == 9374
        assert cfg.pollers == {}

    def test_loads_toml(self, tmp_path: Path, monkeypatch: object) -> None:
        toml = tmp_path / "trigr.toml"
        toml.write_text(
            '[server]\nport = 8080\n\n'
            '[pollers.check]\ninterval = 10\ncommand = "echo ok"\n'
        )
        monkeypatch.setattr("trigr.config.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        cfg = load_config()
        assert cfg.server.port == 8080
        assert "check" in cfg.pollers
        assert cfg.pollers["check"].interval == 10


class TestServerUrl:
    def test_default(self) -> None:
        assert server_url(TrigrConfig()) == "http://127.0.0.1:9374"

    def test_custom(self) -> None:
        cfg = TrigrConfig(server=ServerConfig(host="0.0.0.0", port=8080))
        assert server_url(cfg) == "http://0.0.0.0:8080"

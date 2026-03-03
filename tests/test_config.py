from pathlib import Path

from trigr.config import find_config, load_config


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

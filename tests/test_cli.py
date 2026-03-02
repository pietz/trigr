from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from trigr.cli import app, _parse_delay

runner = CliRunner()


class TestInit:
    def test_creates_file(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / "trigr.toml").exists()
        assert "Created" in result.output

    def test_fails_if_exists(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1
        assert "already exists" in result.output


class TestAdd:
    def test_add_poller(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\nport = 9374\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["add", "checker", "--command", "echo ok", "--interval", "10"])
        assert result.exit_code == 0
        assert "Added" in result.output
        import tomllib
        with open(tmp_path / "trigr.toml", "rb") as f:
            data = tomllib.load(f)
        assert data["pollers"]["checker"]["interval"] == 10
        assert data["pollers"]["checker"]["command"] == "echo ok"

    def test_add_cron(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\nport = 9374\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["add", "daily", "--command", "date", "--cron", "0 9 * * *"])
        assert result.exit_code == 0
        import tomllib
        with open(tmp_path / "trigr.toml", "rb") as f:
            data = tomllib.load(f)
        assert data["crons"]["daily"]["cron"] == "0 9 * * *"

    def test_no_config(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["add", "x", "--command", "echo", "--interval", "5"])
        assert result.exit_code == 1
        assert "No trigr.toml" in result.output

    def test_needs_interval_or_cron(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["add", "x", "--command", "echo"])
        assert result.exit_code == 1

    def test_add_with_message(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\nport = 9374\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["add", "reminder", "--message", "do the thing", "--interval", "60"])
        assert result.exit_code == 0
        import tomllib
        with open(tmp_path / "trigr.toml", "rb") as f:
            data = tomllib.load(f)
        assert "echo" in data["pollers"]["reminder"]["command"]
        assert "do the thing" in data["pollers"]["reminder"]["command"]

    def test_add_with_message_and_command(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\nport = 9374\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["add", "combo", "--message", "context", "--command", "python check.py", "--cron", "0 9 * * *"])
        assert result.exit_code == 0
        import tomllib
        with open(tmp_path / "trigr.toml", "rb") as f:
            data = tomllib.load(f)
        cmd = data["crons"]["combo"]["command"]
        assert "echo" in cmd
        assert "python check.py" in cmd

    def test_add_needs_message_or_command(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["add", "x", "--interval", "5"])
        assert result.exit_code == 1


class TestEmit:
    @patch("trigr.cli._ensure_server_running")
    @patch("trigr.cli.httpx.post")
    def test_emit_success(self, mock_post: MagicMock, mock_ensure: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        mock_post.return_value = MagicMock(status_code=200)
        result = runner.invoke(app, ["emit", "check the weather in Miami"])
        assert result.exit_code == 0
        assert "Emitted" in result.output
        call_json = mock_post.call_args[1]["json"]
        assert call_json["message"] == "check the weather in Miami"

    @patch("trigr.cli._ensure_server_running")
    @patch("trigr.cli.httpx.post")
    def test_emit_with_delay(self, mock_post: MagicMock, mock_ensure: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        mock_post.return_value = MagicMock(status_code=200)
        result = runner.invoke(app, ["emit", "follow up", "--delay", "10s"])
        assert result.exit_code == 0
        call_json = mock_post.call_args[1]["json"]
        assert "fire_at" in call_json


class TestWatch:
    @patch("trigr.cli._ensure_server_running")
    @patch("trigr.cli.httpx.get")
    def test_watch_returns_message(self, mock_get: MagicMock, mock_ensure: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"message": "hello from trigr", "timestamp": "2025-01-01T00:00:00"},
        )
        result = runner.invoke(app, ["watch"])
        assert result.exit_code == 0
        assert result.output.strip() == "hello from trigr"

    @patch("trigr.cli._ensure_server_running")
    @patch("trigr.cli.httpx.get")
    def test_watch_timeout(self, mock_get: MagicMock, mock_ensure: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "timeout"},
        )
        result = runner.invoke(app, ["watch", "--timeout", "1"])
        assert result.exit_code == 1


class TestStatus:
    @patch("trigr.cli._ensure_server_running")
    @patch("trigr.cli.httpx.get")
    def test_status_display(self, mock_get: MagicMock, mock_ensure: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "running", "queue_depth": 0, "pollers": 1, "crons": 0, "jobs": []},
        )
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "running" in result.output


class TestParseDelay:
    def test_seconds(self) -> None:
        before = datetime.now()
        result = _parse_delay("30s")
        assert result >= before + timedelta(seconds=29)

    def test_minutes(self) -> None:
        before = datetime.now()
        result = _parse_delay("5m")
        assert result >= before + timedelta(minutes=4)

    def test_hours(self) -> None:
        before = datetime.now()
        result = _parse_delay("2h")
        assert result >= before + timedelta(hours=1, minutes=59)

    def test_days(self) -> None:
        before = datetime.now()
        result = _parse_delay("1d")
        assert result >= before + timedelta(hours=23)

    def test_invalid(self) -> None:
        import pytest
        with pytest.raises(Exception):
            _parse_delay("abc")

import os
import signal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import tomllib
from typer.testing import CliRunner

from trigr.cli import app, _parse_delay, _validate_cron

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

    def test_init_with_token(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["init", "--token"])
        assert result.exit_code == 0
        content = (tmp_path / "trigr.toml").read_text()
        assert "token = " in content
        assert "# token" not in content  # should be uncommented


class TestAdd:
    def test_add_poller(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\nport = 9374\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["add", "checker", "--command", "echo ok", "--interval", "10"])
        assert result.exit_code == 0
        assert "Added" in result.output
        with open(tmp_path / "trigr.toml", "rb") as f:
            data = tomllib.load(f)
        assert data["pollers"]["checker"]["interval"] == 10
        assert data["pollers"]["checker"]["command"] == "echo ok"

    def test_add_cron(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\nport = 9374\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["add", "daily", "--command", "date", "--cron", "0 9 * * *"])
        assert result.exit_code == 0
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
        with open(tmp_path / "trigr.toml", "rb") as f:
            data = tomllib.load(f)
        assert "echo" in data["pollers"]["reminder"]["command"]
        assert "do the thing" in data["pollers"]["reminder"]["command"]

    def test_add_with_message_and_command(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\nport = 9374\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["add", "combo", "--message", "context", "--command", "python check.py", "--cron", "0 9 * * *"])
        assert result.exit_code == 0
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

    def test_add_invalid_cron(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\nport = 9374\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["add", "bad", "--command", "echo hi", "--cron", "99 99 99 99 99"])
        assert result.exit_code != 0

    def test_add_shows_restart_hint(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\nport = 9374\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["add", "checker", "--command", "echo ok", "--interval", "10"])
        assert result.exit_code == 0
        assert "Restart" in result.output


class TestRemove:
    def test_remove_poller(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text(
            '[server]\nport = 9374\n\n'
            '[pollers.checker]\ninterval = 10\ncommand = "echo ok"\n'
        )
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["remove", "checker"])
        assert result.exit_code == 0
        assert "Removed" in result.output
        with open(tmp_path / "trigr.toml", "rb") as f:
            data = tomllib.load(f)
        assert "checker" not in data.get("pollers", {})

    def test_remove_cron(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text(
            '[server]\nport = 9374\n\n'
            '[crons.daily]\ncron = "0 9 * * *"\ncommand = "date"\n'
        )
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["remove", "daily"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_remove_not_found(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text("[server]\nport = 9374\n")
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["remove", "nope"])
        assert result.exit_code == 1
        assert "nope" in result.output and "found" in result.output.lower()

    def test_remove_no_config(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["remove", "x"])
        assert result.exit_code == 1

    def test_remove_shows_restart_hint(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text(
            '[server]\nport = 9374\n\n'
            '[pollers.checker]\ninterval = 10\ncommand = "echo ok"\n'
        )
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["remove", "checker"])
        assert result.exit_code == 0
        assert "Restart" in result.output


class TestStop:
    @patch("trigr.cli._is_server_running", return_value=False)
    def test_stop_no_server(self, mock_running: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["stop"])
        assert result.exit_code == 0
        assert "No trigr server" in result.output

    @patch("trigr.cli._is_server_running", return_value=False)
    @patch("trigr.cli.os.kill")
    def test_stop_with_pid_file(self, mock_kill: MagicMock, mock_running: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        (tmp_path / ".trigr.pid").write_text("12345")
        result = runner.invoke(app, ["stop"])
        assert result.exit_code == 0
        assert "Stopped" in result.output
        mock_kill.assert_called_once_with(12345, signal.SIGTERM)
        assert not (tmp_path / ".trigr.pid").exists()

    @patch("trigr.cli._is_server_running", return_value=False)
    def test_stop_corrupt_pid_file(self, mock_running: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        (tmp_path / ".trigr.pid").write_text("not-a-number")
        result = runner.invoke(app, ["stop"])
        assert result.exit_code == 0
        assert "Corrupt" in result.output
        assert not (tmp_path / ".trigr.pid").exists()

    @patch("trigr.cli.time.sleep")
    @patch("trigr.cli.os.kill")
    def test_stop_server_still_running(self, mock_kill: MagicMock, mock_sleep: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        monkeypatch.setattr("trigr.cli._is_server_running", lambda port=None: True)
        (tmp_path / ".trigr.pid").write_text("12345")
        result = runner.invoke(app, ["stop"])
        assert result.exit_code == 1
        assert "still running" in result.output


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

    @patch("trigr.cli._ensure_server_running")
    @patch("trigr.cli.httpx.post")
    @patch("trigr.cli.sys")
    def test_emit_stdin(self, mock_sys: MagicMock, mock_post: MagicMock, mock_ensure: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        """Patch entire sys module so CliRunner can't override our stdin mock."""
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        mock_sys.stdin.isatty.return_value = False
        mock_sys.stdin.read.return_value = "hello from stdin"
        mock_sys.argv = ["trigr"]
        mock_post.return_value = MagicMock(status_code=200)
        result = runner.invoke(app, ["emit"])
        assert result.exit_code == 0
        call_json = mock_post.call_args[1]["json"]
        assert call_json["message"] == "hello from stdin"

    @patch("trigr.cli.sys")
    def test_emit_no_message_no_stdin(self, mock_sys: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        """Patch entire sys module so CliRunner can't override our stdin mock."""
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        mock_sys.stdin.isatty.return_value = True
        mock_sys.argv = ["trigr"]
        result = runner.invoke(app, ["emit"])
        assert result.exit_code == 1
        assert "No message" in result.output

    @patch("trigr.cli._ensure_server_running")
    @patch("trigr.cli.httpx.post")
    def test_emit_server_error(self, mock_post: MagicMock, mock_ensure: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        mock_post.return_value = MagicMock(status_code=500)
        result = runner.invoke(app, ["emit", "test"])
        assert result.exit_code == 1
        assert "Server error" in result.output

    @patch("trigr.cli._ensure_server_running")
    @patch("trigr.cli.httpx.post", side_effect=__import__("httpx").ConnectError("refused"))
    def test_emit_connect_error(self, mock_post: MagicMock, mock_ensure: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["emit", "test"])
        assert result.exit_code == 1
        assert "Could not connect" in result.output


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

    @patch("trigr.cli._ensure_server_running")
    @patch("trigr.cli.httpx.get", side_effect=__import__("httpx").ConnectError("refused"))
    def test_watch_connect_error(self, mock_get: MagicMock, mock_ensure: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["watch"])
        assert result.exit_code == 1
        assert "Could not connect" in result.output


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

    @patch("trigr.cli._ensure_server_running")
    @patch("trigr.cli.httpx.get", side_effect=__import__("httpx").ConnectError("refused"))
    def test_status_connect_error(self, mock_get: MagicMock, mock_ensure: MagicMock, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "Could not connect" in result.output


class TestServeAuth:
    def test_serve_refuses_nonlocalhost_without_token(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text('[server]\nhost = "0.0.0.0"\nport = 9374\n')
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        result = runner.invoke(app, ["serve", "-f"])
        assert result.exit_code == 1
        assert "Refusing" in result.output

    def test_serve_allows_nonlocalhost_with_no_auth(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text('[server]\nhost = "0.0.0.0"\nport = 9374\n')
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        mock_uvicorn = MagicMock()
        monkeypatch.setattr("uvicorn.run", mock_uvicorn)
        result = runner.invoke(app, ["serve", "-f", "--no-auth"])
        assert result.exit_code == 0
        assert "WARNING" in result.output

    def test_serve_allows_nonlocalhost_with_token(self, tmp_path: Path, monkeypatch: object) -> None:
        (tmp_path / "trigr.toml").write_text('[server]\nhost = "0.0.0.0"\nport = 9374\ntoken = "secret"\n')
        monkeypatch.setattr("trigr.cli.Path.cwd", lambda: tmp_path)  # type: ignore[attr-defined]
        mock_uvicorn = MagicMock()
        monkeypatch.setattr("uvicorn.run", mock_uvicorn)
        result = runner.invoke(app, ["serve", "-f"])
        assert result.exit_code == 0


class TestParseDelay:
    def test_seconds(self) -> None:
        before = datetime.now(tz=timezone.utc)
        result = _parse_delay("30s")
        assert result >= before + timedelta(seconds=29)

    def test_minutes(self) -> None:
        before = datetime.now(tz=timezone.utc)
        result = _parse_delay("5m")
        assert result >= before + timedelta(minutes=4)

    def test_hours(self) -> None:
        before = datetime.now(tz=timezone.utc)
        result = _parse_delay("2h")
        assert result >= before + timedelta(hours=1, minutes=59)

    def test_days(self) -> None:
        before = datetime.now(tz=timezone.utc)
        result = _parse_delay("1d")
        assert result >= before + timedelta(hours=23)

    def test_invalid(self) -> None:
        with pytest.raises(Exception):
            _parse_delay("abc")


class TestValidateCron:
    def test_valid_cron(self) -> None:
        _validate_cron("0 9 * * *")  # should not raise

    def test_wrong_field_count(self) -> None:
        with pytest.raises(Exception):
            _validate_cron("0 9 *")

    def test_invalid_values(self) -> None:
        with pytest.raises(Exception):
            _validate_cron("99 99 99 99 99")

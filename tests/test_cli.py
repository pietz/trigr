from pathlib import Path

from typer.testing import CliRunner

import trigr.cli as cli


def _write_task(path: Path, name: str = "task-one") -> Path:
    task_file = path / f"{name}.toml"
    task_file.write_text(
        """
name = "task-one"

[trigger]
type = "interval"
interval_seconds = 60

[action]
command = "echo hi"
"""
    )
    return task_file


def test_create_invalid_trigger_has_helpful_error() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        ["create", "demo", "--trigger", "not-a-trigger", "--interval-seconds", "60", "--command", "echo hi"],
    )
    assert result.exit_code != 0
    assert "Invalid value for '--trigger'" in result.output


def test_add_fails_if_launchd_load_fails(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    input_file = _write_task(tmp_path)

    monkeypatch.setattr(cli, "TASKS_DIR", tasks_dir)
    monkeypatch.setattr(cli, "ensure_init", lambda: None)
    monkeypatch.setattr(cli, "write_plist", lambda _task: tmp_path / "mock.plist")
    monkeypatch.setattr(cli, "load_plist", lambda _name: False)

    result = runner.invoke(cli.app, ["add", str(input_file)])
    assert result.exit_code == 1
    assert "failed to load it into launchd" in result.output


def test_create_fails_if_launchd_load_fails(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    monkeypatch.setattr(cli, "TASKS_DIR", tasks_dir)
    monkeypatch.setattr(cli, "ensure_init", lambda: None)
    monkeypatch.setattr(cli, "write_plist", lambda _task: tmp_path / "mock.plist")
    monkeypatch.setattr(cli, "load_plist", lambda _name: False)

    result = runner.invoke(
        cli.app,
        [
            "create",
            "task-one",
            "--trigger",
            "interval",
            "--interval-seconds",
            "60",
            "--command",
            "echo hi",
        ],
    )

    assert result.exit_code == 1
    assert "failed to load it into launchd" in result.output
    assert (tasks_dir / "task-one.toml").exists()


def test_list_warns_about_invalid_task_files(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    _write_task(tasks_dir)
    (tasks_dir / "broken.toml").write_text("not = [valid")

    monkeypatch.setattr(cli, "TASKS_DIR", tasks_dir)
    monkeypatch.setattr(cli, "ensure_init", lambda: None)
    monkeypatch.setattr(cli, "get_runs", lambda _name, limit=1: [])
    monkeypatch.setattr(cli, "is_loaded", lambda _name: False)

    result = runner.invoke(cli.app, ["list"])
    assert result.exit_code == 0
    assert "Warning: skipping invalid task file 'broken.toml'" in result.output
    assert "task-one" in result.output

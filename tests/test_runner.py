import sqlite3
from pathlib import Path

from trigr.config import DB_PATH
from trigr.runner import load_task, run_task


def _write_task_toml(tasks_dir: Path, name: str, command: str) -> None:
    toml = f"""
name = "{name}"
description = "test task"

[trigger]
type = "interval"
interval_seconds = 60

[action]
type = "script"
command = "{command}"
timeout = 10
"""
    (tasks_dir / f"{name}.toml").write_text(toml)


def test_load_task(tmp_path, monkeypatch):
    import trigr.config as cfg
    monkeypatch.setattr(cfg, "TASKS_DIR", tmp_path)
    import trigr.runner as runner_mod
    monkeypatch.setattr(runner_mod, "TASKS_DIR", tmp_path)

    _write_task_toml(tmp_path, "my-task", "echo hello")
    task = load_task("my-task")
    assert task.name == "my-task"
    assert task.action.command == "echo hello"


def test_run_task_success(tmp_path, monkeypatch):
    import trigr.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(cfg, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(cfg, "LOCKS_DIR", tmp_path / "locks")
    monkeypatch.setattr(cfg, "DB_PATH", tmp_path / "history.db")

    import trigr.runner as runner_mod
    monkeypatch.setattr(runner_mod, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(runner_mod, "LOCKS_DIR", tmp_path / "locks")

    import trigr.store as store_mod
    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "history.db")

    # Create dirs and init db
    (tmp_path / "tasks").mkdir()
    (tmp_path / "locks").mkdir()
    cfg.ensure_init()

    _write_task_toml(tmp_path / "tasks", "echo-test", "echo hello world")

    exit_code = run_task("echo-test")
    assert exit_code == 0

    # Check that run was recorded
    con = sqlite3.connect(tmp_path / "history.db")
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM runs WHERE task_name = 'echo-test'").fetchall()
    con.close()
    assert len(rows) == 1
    assert rows[0]["exit_code"] == 0
    assert "hello world" in rows[0]["stdout"]


def test_run_task_failure(tmp_path, monkeypatch):
    import trigr.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(cfg, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(cfg, "LOCKS_DIR", tmp_path / "locks")
    monkeypatch.setattr(cfg, "DB_PATH", tmp_path / "history.db")

    import trigr.runner as runner_mod
    monkeypatch.setattr(runner_mod, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(runner_mod, "LOCKS_DIR", tmp_path / "locks")

    import trigr.store as store_mod
    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "history.db")

    (tmp_path / "tasks").mkdir()
    (tmp_path / "locks").mkdir()
    cfg.ensure_init()

    _write_task_toml(tmp_path / "tasks", "fail-test", "exit 42")

    exit_code = run_task("fail-test")
    assert exit_code == 42

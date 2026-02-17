import sqlite3
from datetime import datetime, timedelta, timezone

from trigr.store import (
    delete_old_runs,
    get_consecutive_failures,
    get_last_output,
    record_run,
)


def _setup(tmp_path, monkeypatch):
    import trigr.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "DB_PATH", tmp_path / "history.db")
    monkeypatch.setattr(cfg, "LOGS_DIR", tmp_path / "logs")

    import trigr.store as store_mod
    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "history.db")

    cfg.ensure_init()
    return tmp_path / "history.db"


def test_get_last_output(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)

    record_run("task-a", now, now, 0, "hello stdout", "hello stderr")
    record_run("task-a", now, now, 0, "latest stdout", "latest stderr")

    result = get_last_output("task-a")
    assert result is not None
    assert result["stdout"] == "latest stdout"
    assert result["stderr"] == "latest stderr"


def test_get_last_output_no_runs(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert get_last_output("nonexistent") is None


def test_delete_old_runs(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    old = datetime.now(timezone.utc) - timedelta(days=60)
    recent = datetime.now(timezone.utc)

    record_run("task-a", old, old, 0, "", "")
    record_run("task-a", recent, recent, 0, "", "")

    deleted = delete_old_runs(30)
    assert deleted == 1

    # Only the recent run should remain
    from trigr.store import get_runs
    runs = get_runs("task-a")
    assert len(runs) == 1


def test_get_consecutive_failures(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)

    # success, fail, fail, fail
    record_run("task-b", now, now, 0, "", "")
    record_run("task-b", now, now, 1, "", "")
    record_run("task-b", now, now, 1, "", "")
    record_run("task-b", now, now, 1, "", "")

    assert get_consecutive_failures("task-b") == 3


def test_get_consecutive_failures_all_success(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)

    record_run("task-c", now, now, 0, "", "")
    record_run("task-c", now, now, 0, "", "")

    assert get_consecutive_failures("task-c") == 0


def test_get_consecutive_failures_no_runs(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert get_consecutive_failures("nonexistent") == 0

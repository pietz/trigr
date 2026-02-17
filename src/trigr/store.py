import sqlite3
from datetime import datetime, timezone

from trigr.config import DB_PATH, LOGS_DIR, ensure_init


def _connect() -> sqlite3.Connection:
    ensure_init()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def record_run(
    task_name: str,
    started_at: datetime,
    finished_at: datetime,
    exit_code: int,
    stdout: str,
    stderr: str,
) -> int:
    """Record a task run. Returns the run ID."""
    # Truncate output to 5KB
    stdout = stdout[:5120]
    stderr = stderr[:5120]
    con = _connect()
    cur = con.execute(
        """INSERT INTO runs (task_name, started_at, finished_at, exit_code, stdout, stderr)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (task_name, started_at.isoformat(), finished_at.isoformat(), exit_code, stdout, stderr),
    )
    con.commit()
    run_id = cur.lastrowid
    con.close()
    return run_id  # type: ignore[return-value]


def get_runs(task_name: str | None = None, limit: int = 20) -> list[dict]:
    """Get recent runs, optionally filtered by task name."""
    con = _connect()
    if task_name:
        rows = con.execute(
            "SELECT * FROM runs WHERE task_name = ? ORDER BY id DESC LIMIT ?",
            (task_name, limit),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_state(task_name: str) -> str | None:
    """Get last stored state value for a task."""
    con = _connect()
    row = con.execute(
        "SELECT last_value FROM state WHERE task_name = ?", (task_name,)
    ).fetchone()
    con.close()
    return row["last_value"] if row else None


def get_last_output(task_name: str) -> dict | None:
    """Get stdout+stderr of the most recent run for a task."""
    con = _connect()
    row = con.execute(
        "SELECT stdout, stderr, exit_code, finished_at FROM runs WHERE task_name = ? ORDER BY id DESC LIMIT 1",
        (task_name,),
    ).fetchone()
    con.close()
    return dict(row) if row else None


def delete_old_runs(days: int) -> int:
    """Delete runs older than N days. Returns count of deleted rows."""
    con = _connect()
    cutoff = datetime.now(timezone.utc).isoformat()
    # Compute cutoff by subtracting days
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur = con.execute("DELETE FROM runs WHERE started_at < ?", (cutoff,))
    deleted = cur.rowcount
    con.commit()
    con.close()
    return deleted


def get_consecutive_failures(task_name: str) -> int:
    """Count consecutive failures from the most recent run backwards."""
    con = _connect()
    rows = con.execute(
        "SELECT exit_code FROM runs WHERE task_name = ? ORDER BY id DESC",
        (task_name,),
    ).fetchall()
    con.close()
    count = 0
    for row in rows:
        if row["exit_code"] != 0:
            count += 1
        else:
            break
    return count


def set_state(task_name: str, value: str) -> None:
    """Set state value for a task."""
    con = _connect()
    con.execute(
        """INSERT INTO state (task_name, last_value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(task_name) DO UPDATE SET last_value = ?, updated_at = ?""",
        (task_name, value, datetime.now(timezone.utc).isoformat(), value, datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()

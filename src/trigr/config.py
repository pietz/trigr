import os
import shutil
import sqlite3
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "trigr"
TASKS_DIR = CONFIG_DIR / "tasks"
LOGS_DIR = CONFIG_DIR / "logs"
LOCKS_DIR = CONFIG_DIR / "locks"
OUTPUTS_DIR = CONFIG_DIR / "outputs"
DB_PATH = CONFIG_DIR / "history.db"
ENV_FILE = CONFIG_DIR / "env"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PREFIX = "com.trigr"

ENV_KEYS = ["PATH", "HOME", "SHELL", "USER", "LANG"]


def init() -> None:
    """Create dirs, capture env, init SQLite."""
    for d in [CONFIG_DIR, TASKS_DIR, LOGS_DIR, LOCKS_DIR, OUTPUTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    PLIST_DIR.mkdir(parents=True, exist_ok=True)

    # Capture environment
    lines: list[str] = []
    for key in ENV_KEYS:
        val = os.environ.get(key, "")
        if val:
            lines.append(f"{key}={val}")
    trigr_path = shutil.which("trigr")
    if trigr_path:
        lines.append(f"TRIGR_PATH={trigr_path}")
    ENV_FILE.write_text("\n".join(lines) + "\n")

    # Init SQLite
    _init_db()


def _init_db() -> None:
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            exit_code INTEGER,
            stdout TEXT,
            stderr TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_name);

        CREATE TABLE IF NOT EXISTS state (
            task_name TEXT PRIMARY KEY,
            last_value TEXT,
            updated_at TEXT
        );
    """)
    con.close()


def ensure_init() -> None:
    """Auto-init if config dir doesn't exist."""
    if not CONFIG_DIR.exists():
        init()
    elif not DB_PATH.exists():
        _init_db()


def load_env() -> dict[str, str]:
    """Load captured environment from env file."""
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line:
                key, _, val = line.partition("=")
                env[key] = val
    return env


def get_trigr_path() -> str:
    """Get the absolute path to the trigr binary."""
    env = load_env()
    if "TRIGR_PATH" in env:
        return env["TRIGR_PATH"]
    path = shutil.which("trigr")
    if path:
        return path
    return "trigr"

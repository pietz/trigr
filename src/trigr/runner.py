import fcntl
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import tomllib

from trigr.config import LOCKS_DIR, TASKS_DIR, ensure_init
from trigr.models import TaskConfig
from trigr.notify import send_notification
from trigr.store import record_run


def load_task(name: str) -> TaskConfig:
    """Load and validate a task from its TOML file."""
    task_path = TASKS_DIR / f"{name}.toml"
    if not task_path.exists():
        raise FileNotFoundError(f"Task not found: {task_path}")
    with open(task_path, "rb") as f:
        data = tomllib.load(f)
    return TaskConfig(**data)


def run_task(name: str) -> int:
    """Execute a task. Returns the exit code."""
    ensure_init()
    task = load_task(name)

    # Acquire file lock (non-blocking)
    lock_path = LOCKS_DIR / f"{name}.lock"
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"Task {name} is already running, skipping.", file=sys.stderr)
        lock_file.close()
        return 0

    started_at = datetime.now(timezone.utc)
    exit_code = 1
    stdout = ""
    stderr = ""

    try:
        # Execute action
        cwd = task.action.working_dir
        if cwd:
            cwd = str(Path(cwd).expanduser().resolve())

        if task.action.type == "script":
            result = subprocess.run(
                task.action.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=task.action.timeout,
                cwd=cwd,
            )
            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr

        elif task.action.type == "claude":
            result = subprocess.run(
                ["claude", "-p", task.action.prompt, "--no-session-persistence"],
                capture_output=True,
                text=True,
                timeout=task.action.timeout,
                cwd=cwd,
            )
            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr

    except subprocess.TimeoutExpired:
        exit_code = 124  # standard timeout exit code
        stderr = f"Task timed out after {task.action.timeout}s"
    except Exception as e:
        exit_code = 1
        stderr = str(e)

    finished_at = datetime.now(timezone.utc)

    # Record to SQLite
    record_run(
        task_name=name,
        started_at=started_at,
        finished_at=finished_at,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
    )

    # Notify
    success = exit_code == 0
    title = task.notify.title or task.name
    if success and task.notify.on_success:
        body = stdout[:200] if stdout else "Completed successfully"
        send_notification(title, body)
    elif not success and task.notify.on_failure:
        body = stderr[:200] if stderr else f"Failed with exit code {exit_code}"
        send_notification(f"FAILED: {title}", body)

    # Release lock
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    lock_file.close()

    return exit_code

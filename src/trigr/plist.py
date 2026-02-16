import plistlib
import subprocess
from pathlib import Path

from trigr.config import LOGS_DIR, PLIST_DIR, PLIST_PREFIX, get_trigr_path, load_env
from trigr.models import TaskConfig, TriggerType


def plist_label(name: str) -> str:
    return f"{PLIST_PREFIX}.{name}"


def plist_path(name: str) -> Path:
    return PLIST_DIR / f"{plist_label(name)}.plist"


def generate_plist(task: TaskConfig) -> dict:
    """Generate a launchd plist dict from a TaskConfig."""
    trigr_path = get_trigr_path()
    env = load_env()
    # Remove TRIGR_PATH from env vars passed to plist
    env.pop("TRIGR_PATH", None)

    plist: dict = {
        "Label": plist_label(task.name),
        "ProgramArguments": [trigr_path, "run", task.name],
        "EnvironmentVariables": env,
        "StandardOutPath": str(LOGS_DIR / f"{task.name}.out.log"),
        "StandardErrorPath": str(LOGS_DIR / f"{task.name}.err.log"),
        "RunAtLoad": False,
    }

    match task.trigger.type:
        case TriggerType.cron:
            cal: dict = {}
            cron = task.trigger.cron
            assert cron is not None
            if cron.minute is not None:
                cal["Minute"] = cron.minute
            if cron.hour is not None:
                cal["Hour"] = cron.hour
            if cron.day is not None:
                cal["Day"] = cron.day
            if cron.weekday is not None:
                cal["Weekday"] = cron.weekday
            if cron.month is not None:
                cal["Month"] = cron.month
            plist["StartCalendarInterval"] = cal

        case TriggerType.interval:
            assert task.trigger.interval_seconds is not None
            plist["StartInterval"] = task.trigger.interval_seconds

        case TriggerType.watch:
            assert task.trigger.watch_paths is not None
            plist["WatchPaths"] = [str(Path(p).expanduser().resolve()) for p in task.trigger.watch_paths]

    return plist


def write_plist(task: TaskConfig) -> Path:
    """Generate and write plist file. Returns the plist path."""
    plist = generate_plist(task)
    path = plist_path(task.name)
    with open(path, "wb") as f:
        plistlib.dump(plist, f)
    return path


def remove_plist(name: str) -> None:
    """Remove plist file if it exists."""
    path = plist_path(name)
    if path.exists():
        path.unlink()


def load_plist(name: str) -> bool:
    """Load (enable) a plist into launchd. Returns True on success."""
    path = plist_path(name)
    if not path.exists():
        return False
    result = subprocess.run(
        ["launchctl", "load", str(path)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def unload_plist(name: str) -> bool:
    """Unload (disable) a plist from launchd. Returns True on success."""
    path = plist_path(name)
    if not path.exists():
        return False
    result = subprocess.run(
        ["launchctl", "unload", str(path)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def is_loaded(name: str) -> bool:
    """Check if a task is currently loaded in launchd."""
    label = plist_label(name)
    result = subprocess.run(
        ["launchctl", "list", label],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0

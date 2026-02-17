import shutil
import subprocess
from pathlib import Path


def send_notification(title: str, body: str, open_path: Path | None = None) -> None:
    """Send a macOS notification. Clicking opens open_path if provided."""
    notifier = shutil.which("terminal-notifier")
    if notifier:
        cmd = [notifier, "-title", title, "-message", body, "-group", "trigr"]
        if open_path:
            cmd.extend(["-open", f"file://{open_path}"])
        subprocess.run(cmd, capture_output=True, timeout=10)
    else:
        # Fallback to osascript
        t = title.replace('"', '\\"')
        b = body.replace('"', '\\"')
        script = f'display notification "{b}" with title "{t}"'
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)

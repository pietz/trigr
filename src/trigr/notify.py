import subprocess


def send_notification(title: str, body: str) -> None:
    """Send a macOS notification via osascript."""
    # Escape double quotes for AppleScript
    title = title.replace('"', '\\"')
    body = body.replace('"', '\\"')
    script = f'display notification "{body}" with title "{title}"'
    subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        timeout=10,
    )

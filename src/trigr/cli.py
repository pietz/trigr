import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from importlib.metadata import version as pkg_version
from pathlib import Path

import httpx
import tomli_w
import tomllib
import typer
from rich.console import Console

app = typer.Typer(help="Event system for AI CLI agents.", no_args_is_help=True)
console = Console()

DEFAULT_PORT = 9374

DEFAULT_CONFIG = """\
[server]
host = "127.0.0.1"
port = 9374

# [pollers.example]
# interval = 60
# command = "echo 'something changed'"

# [crons.example]
# cron = "0 9 * * *"
# command = "echo 'time for the daily report'"
"""


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"trigr {pkg_version('trigr')}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit.",
        callback=_version_callback, is_eager=True,
    ),
) -> None:
    """trigr — event system for AI CLI agents."""


def _config_path() -> Path:
    return Path.cwd() / "trigr.toml"


def _pid_path() -> Path:
    return Path.cwd() / ".trigr.pid"


def _load_toml() -> dict:
    path = _config_path()
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _server_url(port: int | None = None) -> str:
    data = _load_toml()
    server = data.get("server", {})
    host = server.get("host", "127.0.0.1")
    resolved_port = port or server.get("port", DEFAULT_PORT)
    return f"http://{host}:{resolved_port}"


def _parse_delay(delay: str) -> datetime:
    """Convert '48h', '30m', '5s' to absolute datetime."""
    match = re.fullmatch(r"(\d+)([smhd])", delay.strip())
    if not match:
        raise typer.BadParameter(f"Invalid delay format: {delay!r} (use e.g. 10s, 5m, 2h, 1d)")
    value = int(match.group(1))
    unit = match.group(2)
    delta = {"s": timedelta(seconds=value), "m": timedelta(minutes=value),
             "h": timedelta(hours=value), "d": timedelta(days=value)}[unit]
    return datetime.now() + delta


def _start_detached(port: int | None = None) -> int:
    """Spawn 'trigr serve -f' as a background process. Returns PID."""
    trigr_bin = sys.argv[0] if os.path.isfile(sys.argv[0]) else "trigr"
    cmd = [trigr_bin, "serve", "-f"]
    if port:
        cmd.extend(["--port", str(port)])
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        cwd=Path.cwd(),
    )
    _pid_path().write_text(str(proc.pid))
    return proc.pid


def _is_server_running(port: int | None = None) -> bool:
    """Check if server is reachable."""
    try:
        resp = httpx.get(f"{_server_url(port)}/status", timeout=2)
        return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def _ensure_config() -> None:
    """Create trigr.toml with defaults if it doesn't exist."""
    path = _config_path()
    if not path.exists():
        path.write_text(DEFAULT_CONFIG)


def _ensure_server_running(port: int | None = None) -> None:
    """Auto-start server if not running, wait up to 3s."""
    _ensure_config()
    if _is_server_running(port):
        return
    pid = _start_detached(port)
    console.print(f"Started trigr server (PID {pid})", style="dim")
    for _ in range(30):
        time.sleep(0.1)
        if _is_server_running(port):
            return
    console.print("Warning: server may not have started in time.", style="yellow")


@app.command(name="init")
def init_cmd() -> None:
    """Create trigr.toml in the current directory."""
    path = _config_path()
    if path.exists():
        console.print("trigr.toml already exists.", style="red")
        raise typer.Exit(1)
    path.write_text(DEFAULT_CONFIG)
    console.print("Created trigr.toml", style="green")


@app.command()
def serve(
    foreground: bool = typer.Option(False, "-f", "--foreground", help="Run in foreground"),
    port: int | None = typer.Option(None, "--port", "-p", help="Port to listen on"),
) -> None:
    """Start the trigr server."""
    if foreground:
        import uvicorn
        from trigr.config import load_config
        config = load_config()
        resolved_port = port or config.server.port
        uvicorn.run(
            "trigr.server:app",
            host=config.server.host,
            port=resolved_port,
            log_level="info",
        )
    else:
        _ensure_config()
        pid = _start_detached(port)
        console.print(f"trigr server started (PID {pid})", style="green")
        time.sleep(0.5)
        if _is_server_running(port):
            console.print(f"Listening on {_server_url(port)}", style="dim")
        else:
            console.print("Warning: server may not have started yet.", style="yellow")


@app.command()
def watch(
    timeout: int = typer.Option(300, "--timeout", "-t", help="Timeout in seconds"),
    port: int | None = typer.Option(None, "--port", "-p", help="Server port"),
) -> None:
    """Block until a message arrives, print it, then exit."""
    _ensure_server_running(port)
    try:
        resp = httpx.get(
            f"{_server_url(port)}/next",
            params={"timeout": timeout},
            timeout=timeout + 5,
        )
        data = resp.json()
        if data.get("status") == "timeout":
            raise typer.Exit(1)
        typer.echo(data["message"])
    except httpx.ConnectError:
        console.print("Could not connect to trigr server.", style="red")
        raise typer.Exit(1)


@app.command()
def emit(
    message: str = typer.Argument(..., help="Message to send to the agent"),
    delay: str | None = typer.Option(None, "--delay", help="Delay before delivery (e.g. 10s, 5m, 2h)"),
    port: int | None = typer.Option(None, "--port", "-p", help="Server port"),
) -> None:
    """Send a message to the agent."""
    _ensure_server_running(port)

    payload: dict = {"message": message}
    if delay:
        payload["fire_at"] = _parse_delay(delay).isoformat()

    try:
        resp = httpx.post(f"{_server_url(port)}/emit", json=payload, timeout=5)
        if resp.status_code == 200:
            console.print("Emitted", style="green")
        else:
            console.print(f"Server error: {resp.status_code}", style="red")
            raise typer.Exit(1)
    except httpx.ConnectError:
        console.print("Could not connect to trigr server.", style="red")
        raise typer.Exit(1)


@app.command(name="add")
def add_cmd(
    name: str = typer.Argument(..., help="Name for the poller/cron"),
    command: str | None = typer.Option(None, "--command", "-c", help="Command to run (stdout becomes the message)"),
    message: str | None = typer.Option(None, "--message", "-m", help="Static message to deliver"),
    interval: int | None = typer.Option(None, "--interval", "-i", help="Interval in seconds (poller)"),
    cron: str | None = typer.Option(None, "--cron", help="Cron expression (5-field)"),
) -> None:
    """Add a poller or cron job to trigr.toml."""
    if not interval and not cron:
        console.print("Provide either --interval or --cron.", style="red")
        raise typer.Exit(1)
    if interval and cron:
        console.print("Provide only one of --interval or --cron.", style="red")
        raise typer.Exit(1)
    if not command and not message:
        console.print("Provide either --command or --message (or both).", style="red")
        raise typer.Exit(1)

    # Build command: message first, then command output
    parts = []
    if message:
        escaped = message.replace("'", "'\\''")
        parts.append(f"echo '{escaped}'")
    if command:
        parts.append(command)
    resolved_command = " && ".join(parts)

    path = _config_path()
    if not path.exists():
        console.print("No trigr.toml found. Run 'trigr init' first.", style="red")
        raise typer.Exit(1)

    with open(path, "rb") as f:
        data = tomllib.load(f)

    if interval:
        pollers = data.setdefault("pollers", {})
        if name in pollers:
            console.print(f"Poller '{name}' already exists.", style="red")
            raise typer.Exit(1)
        pollers[name] = {"interval": interval, "command": resolved_command}
        label = f"poller '{name}' (every {interval}s)"
    else:
        crons = data.setdefault("crons", {})
        if name in crons:
            console.print(f"Cron '{name}' already exists.", style="red")
            raise typer.Exit(1)
        crons[name] = {"cron": cron, "command": resolved_command}
        label = f"cron '{name}' ({cron})"

    path.write_bytes(tomli_w.dumps(data).encode())
    console.print(f"Added {label}", style="green")


@app.command()
def status(
    port: int | None = typer.Option(None, "--port", "-p", help="Server port"),
) -> None:
    """Show server status."""
    _ensure_server_running(port)
    try:
        resp = httpx.get(f"{_server_url(port)}/status", timeout=5)
        data = resp.json()
        console.print(f"Status: [green]{data['status']}[/green]")
        console.print(f"Queue depth: {data['queue_depth']}")
        console.print(f"Pollers: {data['pollers']}")
        console.print(f"Crons: {data['crons']}")
        if data.get("jobs"):
            console.print("\nScheduled jobs:")
            for job in data["jobs"]:
                next_run = job.get("next_run") or "N/A"
                console.print(f"  {job['name']} — next: {next_run}")
    except httpx.ConnectError:
        console.print("Could not connect to trigr server.", style="red")
        raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

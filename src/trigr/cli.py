import os
import re
import secrets
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
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
# token = "your-secret-token"

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


def _log_path() -> Path:
    return Path.cwd() / ".trigr.log"


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


def _auth_headers() -> dict[str, str]:
    """Return Authorization header if token is configured."""
    data = _load_toml()
    token = data.get("server", {}).get("token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _parse_delay(delay: str) -> datetime:
    """Convert '48h', '30m', '5s' to absolute datetime."""
    match = re.fullmatch(r"(\d+)([smhd])", delay.strip())
    if not match:
        raise typer.BadParameter(f"Invalid delay format: {delay!r} (use e.g. 10s, 5m, 2h, 1d)")
    value = int(match.group(1))
    unit = match.group(2)
    delta = {"s": timedelta(seconds=value), "m": timedelta(minutes=value),
             "h": timedelta(hours=value), "d": timedelta(days=value)}[unit]
    return datetime.now(tz=timezone.utc) + delta


def _find_job(name: str) -> tuple[str, dict]:
    """Look up a poller or cron by name. Returns (section, config) or exits."""
    data = _load_toml()
    for section in ("pollers", "crons"):
        jobs = data.get(section, {})
        if name in jobs:
            return section, jobs[name]
    console.print(f"No poller or cron named '{name}' found.", style="red")
    raise typer.Exit(1)


def _validate_cron(expr: str) -> None:
    """Validate a 5-field cron expression at add-time."""
    from apscheduler.triggers.cron import CronTrigger

    parts = expr.strip().split()
    if len(parts) != 5:
        raise typer.BadParameter(f"Expected 5-field cron expression, got {len(parts)} fields: {expr!r}")
    minute, hour, day, month, day_of_week = parts
    try:
        CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)
    except (ValueError, KeyError) as e:
        raise typer.BadParameter(f"Invalid cron expression {expr!r}: {e}")


def _start_detached(port: int | None = None, verbose: bool = False, no_auth: bool = False) -> int:
    """Spawn 'trigr serve -f' as a background process. Returns PID."""
    trigr_bin = sys.argv[0] if os.path.isfile(sys.argv[0]) else "trigr"
    cmd = [trigr_bin, "serve", "-f"]
    if port:
        cmd.extend(["--port", str(port)])
    if verbose:
        cmd.append("--verbose")
    if no_auth:
        cmd.append("--no-auth")
    log_file = open(_log_path(), "a")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=log_file,
        start_new_session=True,
        cwd=Path.cwd(),
    )
    log_file.close()
    _pid_path().write_text(str(proc.pid))
    return proc.pid


def _is_server_running(port: int | None = None) -> bool:
    """Check if server is reachable."""
    try:
        resp = httpx.get(f"{_server_url(port)}/status", timeout=2, headers=_auth_headers())
        return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def _ensure_config() -> None:
    """Create trigr.toml with defaults if it doesn't exist."""
    path = _config_path()
    if not path.exists():
        path.write_text(DEFAULT_CONFIG)


def _ensure_server_running(port: int | None = None, verbose: bool = False) -> None:
    """Auto-start server if not running, wait up to 3s."""
    _ensure_config()
    if _is_server_running(port):
        return
    # Clean up stale PID file if the process is no longer alive
    try:
        old_pid = int(_pid_path().read_text().strip())
        os.kill(old_pid, 0)  # check if alive (no signal sent)
        return  # process exists — server may be starting up
    except (FileNotFoundError, ValueError, ProcessLookupError):
        _pid_path().unlink(missing_ok=True)
    pid = _start_detached(port, verbose=verbose)
    console.print(f"Started trigr server (PID {pid})", style="dim")
    for _ in range(30):
        time.sleep(0.1)
        if _is_server_running(port):
            return
    console.print(f"Warning: server may not have started. Check {_log_path()} for details.", style="yellow")


@app.command(name="init")
def init_cmd(
    token: bool = typer.Option(False, "--token", help="Generate a random auth token"),
) -> None:
    """Create trigr.toml in the current directory."""
    path = _config_path()
    if path.exists():
        console.print("trigr.toml already exists.", style="red")
        raise typer.Exit(1)
    if token:
        generated = secrets.token_urlsafe(32)
        config_text = DEFAULT_CONFIG.replace(
            '# token = "your-secret-token"',
            f'token = "{generated}"',
        )
        path.write_text(config_text)
        console.print(f"Created trigr.toml with auth token", style="green")
    else:
        path.write_text(DEFAULT_CONFIG)
        console.print("Created trigr.toml", style="green")


@app.command()
def serve(
    foreground: bool = typer.Option(False, "-f", "--foreground", help="Run in foreground"),
    port: int | None = typer.Option(None, "--port", "-p", help="Port to listen on"),
    no_auth: bool = typer.Option(False, "--no-auth", help="Allow non-localhost without token (unsafe)"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug logging"),
) -> None:
    """Start the trigr server."""
    if foreground:
        import logging
        import uvicorn
        from trigr.config import load_config

        if verbose:
            logging.getLogger("trigr").setLevel(logging.DEBUG)

        config = load_config()
        resolved_port = port or config.server.port

        # Refuse to bind non-localhost without auth
        is_localhost = config.server.host in ("127.0.0.1", "localhost")
        if not is_localhost and not config.server.token and not no_auth:
            console.print(
                "Refusing to bind to non-localhost without a token.\n"
                "Set 'token' in trigr.toml or pass --no-auth to override.",
                style="red",
            )
            raise typer.Exit(1)
        if not is_localhost and not config.server.token and no_auth:
            console.print(
                "WARNING: Running without auth on a non-localhost address. "
                "Anyone on the network can send events.",
                style="bold yellow",
            )

        uvicorn.run(
            "trigr.server:app",
            host=config.server.host,
            port=resolved_port,
            log_level="debug" if verbose else "info",
        )
    else:
        _ensure_config()
        pid = _start_detached(port, verbose=verbose, no_auth=no_auth)
        console.print(f"trigr server started (PID {pid})", style="green")
        time.sleep(0.5)
        if _is_server_running(port):
            console.print(f"Listening on {_server_url(port)}", style="dim")
        else:
            console.print(f"Warning: server may not have started. Check {_log_path()} for details.", style="yellow")


@app.command()
def stop(
    port: int | None = typer.Option(None, "--port", "-p", help="Server port"),
) -> None:
    """Stop the trigr server."""
    pid_file = _pid_path()

    if not _is_server_running(port) and not pid_file.exists():
        console.print("No trigr server is running.", style="yellow")
        return

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
        except ValueError:
            pid_file.unlink()
            console.print("Corrupt PID file removed.", style="yellow")
            return

        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        for _ in range(30):
            time.sleep(0.1)
            if not _is_server_running(port):
                break

    if _is_server_running(port):
        console.print("Server is still running.", style="red")
        raise typer.Exit(1)

    pid_file.unlink(missing_ok=True)
    console.print("Stopped trigr server.", style="green")


@app.command()
def watch(
    timeout: int = typer.Option(0, "--timeout", "-t", help="Timeout in seconds (0 = wait forever)"),
    port: int | None = typer.Option(None, "--port", "-p", help="Server port"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug logging on auto-started server"),
) -> None:
    """Block until a message arrives, print it, then exit."""
    _ensure_server_running(port, verbose=verbose)
    params = {"timeout": timeout} if timeout > 0 else {}
    http_timeout = timeout + 5 if timeout > 0 else None
    try:
        resp = httpx.get(
            f"{_server_url(port)}/next",
            params=params,
            timeout=http_timeout,
            headers=_auth_headers(),
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
    message: str | None = typer.Argument(None, help="Message to send (reads stdin if omitted)"),
    delay: str | None = typer.Option(None, "--delay", help="Delay before delivery (e.g. 10s, 5m, 2h)"),
    port: int | None = typer.Option(None, "--port", "-p", help="Server port"),
) -> None:
    """Send a message to the agent."""
    if message is None:
        if not sys.stdin.isatty():
            message = sys.stdin.read().strip()
        if not message:
            console.print("No message provided. Pass as argument or pipe via stdin.", style="red")
            raise typer.Exit(1)

    _ensure_server_running(port)

    payload: dict = {"message": message}
    if delay:
        payload["fire_at"] = _parse_delay(delay).isoformat()

    try:
        resp = httpx.post(
            f"{_server_url(port)}/emit",
            json=payload,
            timeout=5,
            headers=_auth_headers(),
        )
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
    if interval is None and not cron:
        console.print("Provide either --interval or --cron.", style="red")
        raise typer.Exit(1)
    if interval is not None and cron:
        console.print("Provide only one of --interval or --cron.", style="red")
        raise typer.Exit(1)
    if not command and not message:
        console.print("Provide either --command or --message (or both).", style="red")
        raise typer.Exit(1)

    if cron:
        _validate_cron(cron)

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

    if interval is not None:
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
    console.print(f"Added {label}. Restart the server to apply.", style="green")


@app.command(name="remove")
def remove_cmd(
    name: str = typer.Argument(..., help="Name of the poller/cron to remove"),
) -> None:
    """Remove a poller or cron job from trigr.toml."""
    section, _ = _find_job(name)

    path = _config_path()
    with open(path, "rb") as f:
        data = tomllib.load(f)

    del data[section][name]
    path.write_bytes(tomli_w.dumps(data).encode())
    console.print(f"Removed '{name}'. Restart the server to apply.", style="green")


@app.command()
def run(
    name: str = typer.Argument(..., help="Name of the poller/cron to run"),
) -> None:
    """Run a poller or cron command once and show its output."""
    _, job = _find_job(name)
    command = job["command"]

    console.print(f"Running: {command}", style="dim")
    result = subprocess.run(command, shell=True, capture_output=True, timeout=30)

    stdout = result.stdout.decode().strip()
    stderr = result.stderr.decode().strip()

    if stderr:
        console.print(f"[bold]stderr:[/bold]\n{stderr}")

    if not stdout:
        console.print("No output (empty stdout → no event would be created).", style="yellow")
        return

    console.print(f"[bold]output:[/bold]\n{stdout}")
    console.print(f"\n[green]This output ({len(stdout)} chars) would become an event message.[/green]")


@app.command(name="list")
def list_cmd() -> None:
    """List configured pollers and crons from trigr.toml."""
    data = _load_toml()
    pollers = data.get("pollers", {})
    crons = data.get("crons", {})

    if not pollers and not crons:
        console.print("No pollers or crons configured.", style="yellow")
        return

    if pollers:
        console.print("[bold]Pollers:[/bold]")
        for name, cfg in pollers.items():
            console.print(f"  {name} — every {cfg['interval']}s — {cfg['command']}")

    if crons:
        console.print("[bold]Crons:[/bold]")
        for name, cfg in crons.items():
            console.print(f"  {name} — {cfg['cron']} — {cfg['command']}")


@app.command()
def status(
    port: int | None = typer.Option(None, "--port", "-p", help="Server port"),
) -> None:
    """Show server status."""
    if not _is_server_running(port):
        console.print("Server is not running.", style="yellow")
        raise typer.Exit(1)
    try:
        resp = httpx.get(f"{_server_url(port)}/status", timeout=5, headers=_auth_headers())
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

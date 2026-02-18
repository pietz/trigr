import fcntl
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from importlib.metadata import version as pkg_version
from pathlib import Path

import tomli_w
import tomllib
import typer
from rich.console import Console
from rich.table import Table

from trigr.config import LOCKS_DIR, LOGS_DIR, TASKS_DIR, ensure_init, init
from trigr.models import ActionConfig, CronSchedule, NotifyConfig, TaskConfig, TriggerConfig, TriggerType
from trigr.plist import is_loaded, load_plist, plist_path, remove_plist, unload_plist, write_plist
from trigr.runner import run_task
from trigr.store import delete_old_runs, get_last_output, get_runs


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"trigr {pkg_version('trigr')}")
        raise typer.Exit()


app = typer.Typer(help="Compile task specs into launchd schedules.", no_args_is_help=True)
console = Console()


@app.callback()
def _main(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit.",
        callback=_version_callback, is_eager=True,
    ),
) -> None:
    """trigr — lightweight launchd task scheduler."""


def _load_task_from_file(path: Path) -> TaskConfig:
    """Load and validate a task config from a TOML file."""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return TaskConfig(**data)


def _all_tasks() -> list[TaskConfig]:
    """Load all task configs from the tasks directory."""
    tasks: list[TaskConfig] = []
    for toml_file in sorted(TASKS_DIR.glob("*.toml")):
        try:
            tasks.append(_load_task_from_file(toml_file))
        except Exception:
            pass
    return tasks


@app.command(name="init")
def init_cmd() -> None:
    """Initialize trigr: create dirs, capture env, init database."""
    init()
    console.print("Initialized trigr.", style="green")


@app.command()
def add(file: Path) -> None:
    """Register a task from a TOML file, generate plist, and load into launchd."""
    ensure_init()
    if not file.exists():
        console.print(f"File not found: {file}", style="red")
        raise typer.Exit(1)

    task = _load_task_from_file(file)

    # Copy TOML to tasks dir
    dest = TASKS_DIR / f"{task.name}.toml"
    if dest.exists():
        console.print(f"Task '{task.name}' already exists. Use 'trigr remove' first.", style="red")
        raise typer.Exit(1)

    shutil.copy2(file, dest)

    # Generate and write plist
    plist_file = write_plist(task)

    # Load into launchd if enabled
    if task.enabled:
        load_plist(task.name)
        console.print(f"Added and loaded task '{task.name}'.", style="green")
    else:
        console.print(f"Added task '{task.name}' (disabled).", style="yellow")

    console.print(f"  TOML: {dest}")
    console.print(f"  Plist: {plist_file}")


@app.command()
def remove(name: str) -> None:
    """Unload and remove a task (plist + task file)."""
    ensure_init()
    task_file = TASKS_DIR / f"{name}.toml"

    if not task_file.exists():
        console.print(f"Task '{name}' not found.", style="red")
        raise typer.Exit(1)

    # Unload from launchd
    unload_plist(name)
    remove_plist(name)
    task_file.unlink()
    console.print(f"Removed task '{name}'.", style="green")


@app.command()
def enable(name: str) -> None:
    """Load a task into launchd."""
    ensure_init()
    task_file = TASKS_DIR / f"{name}.toml"
    if not task_file.exists():
        console.print(f"Task '{name}' not found.", style="red")
        raise typer.Exit(1)

    # Regenerate plist in case it's missing
    task = _load_task_from_file(task_file)
    write_plist(task)

    if load_plist(name):
        console.print(f"Enabled task '{name}'.", style="green")
    else:
        console.print(f"Failed to enable task '{name}'.", style="red")
        raise typer.Exit(1)


@app.command()
def disable(name: str) -> None:
    """Unload a task from launchd."""
    ensure_init()
    if unload_plist(name):
        console.print(f"Disabled task '{name}'.", style="green")
    else:
        console.print(f"Failed to disable task '{name}'.", style="red")
        raise typer.Exit(1)


@app.command(name="list")
def list_cmd(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all tasks with status and last run info."""
    ensure_init()
    tasks = _all_tasks()

    if as_json:
        output = []
        for task in tasks:
            runs = get_runs(task.name, limit=1)
            last_run = runs[0] if runs else None
            output.append({
                "name": task.name,
                "description": task.description,
                "trigger": task.trigger.type.value,
                "action": (task.action.provider or "claude") if task.action.prompt else "script",
                "enabled": task.enabled,
                "loaded": is_loaded(task.name),
                "last_run": last_run,
            })
        typer.echo(json.dumps(output, indent=2))
        return

    if not tasks:
        console.print("No tasks registered.", style="yellow")
        return

    table = Table(title="Scheduled Tasks")
    table.add_column("Name", style="cyan")
    table.add_column("Trigger")
    table.add_column("Action")
    table.add_column("Status")
    table.add_column("Last Run")

    for task in tasks:
        loaded = is_loaded(task.name)
        status = "[green]loaded[/green]" if loaded else "[yellow]unloaded[/yellow]"

        runs = get_runs(task.name, limit=1)
        if runs:
            last = runs[0]
            code = last["exit_code"]
            color = "green" if code == 0 else "red"
            last_run = f"[{color}]exit {code}[/{color}] @ {last['finished_at'][:19]}"
        else:
            last_run = "[dim]never[/dim]"

        action_label = (task.action.provider or "claude") if task.action.prompt else "script"
        table.add_row(
            task.name,
            task.trigger.type.value,
            action_label,
            status,
            last_run,
        )

    console.print(table)


@app.command()
def show(
    name: str,
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show full task configuration."""
    ensure_init()
    task_file = TASKS_DIR / f"{name}.toml"
    if not task_file.exists():
        console.print(f"Task '{name}' not found.", style="red")
        raise typer.Exit(1)

    task = _load_task_from_file(task_file)

    if as_json:
        typer.echo(task.model_dump_json(indent=2))
        return

    console.print(f"[bold cyan]{task.name}[/bold cyan]")
    if task.description:
        console.print(f"  {task.description}")
    console.print(f"  Trigger: {task.trigger.type.value}")
    action_label = (task.action.provider or "claude") if task.action.prompt else "script"
    console.print(f"  Action:  {action_label}")
    console.print(f"  Timeout: {task.action.timeout}s")
    console.print(f"  Loaded:  {is_loaded(name)}")
    console.print(f"  Plist:   {plist_path(name)}")
    console.print(f"  TOML:    {task_file}")


@app.command()
def logs(
    name: str | None = typer.Argument(None, help="Task name (all tasks if omitted)"),
    n: int = typer.Option(20, "-n", help="Number of entries"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show run history from SQLite."""
    ensure_init()
    runs = get_runs(name, limit=n)

    if as_json:
        typer.echo(json.dumps(runs, indent=2))
        return

    if not runs:
        console.print("No runs recorded.", style="yellow")
        return

    table = Table(title="Run History")
    table.add_column("ID", style="dim")
    table.add_column("Task", style="cyan")
    table.add_column("Started")
    table.add_column("Duration")
    table.add_column("Exit")

    for run in runs:
        code = run["exit_code"]
        exit_style = "green" if code == 0 else "red"

        started = run["started_at"][:19]
        # Compute duration
        if run["finished_at"] and run["started_at"]:
            from datetime import datetime
            try:
                s = datetime.fromisoformat(run["started_at"])
                f = datetime.fromisoformat(run["finished_at"])
                dur = f"{(f - s).total_seconds():.1f}s"
            except Exception:
                dur = "?"
        else:
            dur = "?"

        table.add_row(
            str(run["id"]),
            run["task_name"],
            started,
            dur,
            f"[{exit_style}]{code}[/{exit_style}]",
        )

    console.print(table)


@app.command()
def run(name: str) -> None:
    """Execute a task immediately (runner entrypoint for launchd)."""
    ensure_init()
    exit_code = run_task(name)
    raise typer.Exit(exit_code)


@app.command()
def edit(name: str) -> None:
    """Open task TOML in $EDITOR, re-validate and regenerate plist on save."""
    ensure_init()
    task_file = TASKS_DIR / f"{name}.toml"
    if not task_file.exists():
        console.print(f"Task '{name}' not found.", style="red")
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR", "nano")

    # Copy to temp file for editing
    content_before = task_file.read_text()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as tmp:
        tmp.write(content_before)
        tmp_path = tmp.name

    try:
        subprocess.run([editor, tmp_path], check=True)
        content_after = Path(tmp_path).read_text()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if content_after == content_before:
        console.print("No changes made.", style="yellow")
        return

    # Validate new content
    try:
        import tomllib as tl
        task = TaskConfig(**tl.loads(content_after))
    except Exception as e:
        console.print(f"Invalid config: {e}", style="red")
        console.print("Changes discarded.", style="yellow")
        raise typer.Exit(1)

    # Save and regenerate
    was_loaded = is_loaded(name)
    if was_loaded:
        unload_plist(name)

    task_file.write_text(content_after)
    write_plist(task)

    if was_loaded:
        load_plist(task.name)

    console.print(f"Updated task '{name}'.", style="green")


@app.command()
def refresh() -> None:
    """Re-capture env, regenerate and reload all plists."""
    init()
    tasks = _all_tasks()
    count = 0
    for task in tasks:
        was_loaded = is_loaded(task.name)
        unload_plist(task.name)
        write_plist(task)
        if was_loaded:
            load_plist(task.name)
        count += 1
    console.print(f"Refreshed {count} tasks.", style="green")


@app.command()
def output(
    name: str,
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    show_stderr: bool = typer.Option(False, "--stderr", help="Show stderr instead of stdout"),
) -> None:
    """Show last run's output for a task."""
    ensure_init()
    result = get_last_output(name)
    if result is None:
        console.print("No runs recorded.", style="yellow")
        raise typer.Exit(1)

    if as_json:
        typer.echo(json.dumps(result, indent=2))
        return

    text = result["stderr"] if show_stderr else result["stdout"]
    if text:
        typer.echo(text)
    else:
        console.print("(empty)", style="dim")


@app.command()
def validate(file: Path) -> None:
    """Validate a TOML task file without registering it."""
    if not file.exists():
        console.print(f"File not found: {file}", style="red")
        raise typer.Exit(1)
    try:
        task = _load_task_from_file(file)
        console.print(f"Valid: task '{task.name}'", style="green")
    except Exception as e:
        console.print(f"Invalid: {e}", style="red")
        raise typer.Exit(1)


@app.command()
def status(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show currently-running tasks by checking lock files."""
    ensure_init()
    running: list[dict] = []

    for lock_file in LOCKS_DIR.glob("*.lock"):
        task_name = lock_file.stem
        try:
            fd = open(lock_file)
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Lock acquired = not running, release immediately
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            fd.close()
        except BlockingIOError:
            mtime = datetime.fromtimestamp(lock_file.stat().st_mtime)
            running.append({
                "name": task_name,
                "running_since": mtime.isoformat(),
            })
            fd.close()

    if as_json:
        typer.echo(json.dumps(running, indent=2))
        return

    if not running:
        console.print("No tasks currently running.", style="dim")
        return

    table = Table(title="Running Tasks")
    table.add_column("Task", style="cyan")
    table.add_column("Running Since")
    for r in running:
        table.add_row(r["name"], r["running_since"][:19])
    console.print(table)


@app.command()
def clean(
    older_than: int = typer.Option(30, "--older-than", help="Delete runs older than N days"),
) -> None:
    """Purge old run data from the database and truncate log files."""
    ensure_init()
    deleted = delete_old_runs(older_than)

    # Truncate old log files
    cleaned = 0
    if LOGS_DIR.exists():
        cutoff = datetime.now().timestamp() - older_than * 86400
        for log_file in LOGS_DIR.glob("*.log"):
            if log_file.stat().st_mtime < cutoff:
                log_file.write_text("")
                cleaned += 1

    console.print(f"Deleted {deleted} runs, cleaned {cleaned} log files.", style="green")


@app.command()
def create(
    name: str,
    # Trigger options
    trigger: str = typer.Option(..., help="Trigger type: cron, interval, or watch"),
    hour: int | None = typer.Option(None, help="Cron hour (0-23)"),
    minute: int | None = typer.Option(None, help="Cron minute (0-59)"),
    day: int | None = typer.Option(None, help="Cron day of month (1-31)"),
    weekday: int | None = typer.Option(None, help="Cron weekday (0=Sun)"),
    month: int | None = typer.Option(None, help="Cron month (1-12)"),
    interval_seconds: int | None = typer.Option(None, "--interval-seconds", help="Interval in seconds"),
    watch_paths: list[str] | None = typer.Option(None, "--watch-path", help="Paths to watch"),
    # Action options
    command: str | None = typer.Option(None, help="Script command"),
    prompt: str | None = typer.Option(None, help="LLM prompt"),
    provider: str | None = typer.Option(None, help="LLM provider: claude, codex, or gemini"),
    model: str | None = typer.Option(None, help="Override default model for provider"),
    working_dir: str | None = typer.Option(None, "--working-dir", help="Working directory"),
    timeout: int = typer.Option(300, help="Timeout in seconds"),
    # Notify options
    notify_on_success: bool = typer.Option(False, "--notify-on-success", help="Notify on success"),
    notify_on_failure: bool = typer.Option(True, "--notify-on-failure", help="Notify on failure"),
    notify_title: str | None = typer.Option(None, "--notify-title", help="Custom notification title"),
    max_consecutive_failures: int = typer.Option(0, "--max-failures", help="Auto-disable after N failures (0=never)"),
    # Task options
    description: str = typer.Option("", help="Task description"),
) -> None:
    """Create a task inline without writing a TOML file first."""
    ensure_init()

    # Build trigger config
    trigger_type = TriggerType(trigger)
    cron_schedule = None
    if trigger_type == TriggerType.cron:
        cron_schedule = CronSchedule(
            minute=minute, hour=hour, day=day, weekday=weekday, month=month,
        )
    trigger_config = TriggerConfig(
        type=trigger_type,
        cron=cron_schedule,
        interval_seconds=interval_seconds,
        watch_paths=watch_paths,
    )

    # Build action config
    action_config = ActionConfig(
        command=command,
        prompt=prompt,
        provider=provider,
        model=model,
        working_dir=working_dir,
        timeout=timeout,
    )

    # Build notify config
    notify_config = NotifyConfig(
        on_success=notify_on_success,
        on_failure=notify_on_failure,
        title=notify_title,
        max_consecutive_failures=max_consecutive_failures,
    )

    # Build and validate task
    try:
        task = TaskConfig(
            name=name,
            description=description,
            trigger=trigger_config,
            action=action_config,
            notify=notify_config,
        )
    except Exception as e:
        console.print(f"Invalid config: {e}", style="red")
        raise typer.Exit(1)

    # Write TOML
    dest = TASKS_DIR / f"{name}.toml"
    if dest.exists():
        console.print(f"Task '{name}' already exists. Use 'trigr remove' first.", style="red")
        raise typer.Exit(1)

    # Serialize to TOML
    data: dict = {"name": name}
    if description:
        data["description"] = description

    trigger_data: dict = {"type": trigger}
    if trigger_type == TriggerType.interval:
        trigger_data["interval_seconds"] = interval_seconds
    elif trigger_type == TriggerType.watch and watch_paths:
        trigger_data["watch_paths"] = watch_paths
    if trigger_type == TriggerType.cron and cron_schedule:
        cron_data = {}
        for field in ("minute", "hour", "day", "weekday", "month"):
            val = getattr(cron_schedule, field)
            if val is not None:
                cron_data[field] = val
        trigger_data["cron"] = cron_data
    data["trigger"] = trigger_data

    action_data: dict = {}
    if command:
        action_data["command"] = command
    if prompt:
        action_data["prompt"] = prompt
    if provider:
        action_data["provider"] = provider
    if model:
        action_data["model"] = model
    if working_dir:
        action_data["working_dir"] = working_dir
    if timeout != 300:
        action_data["timeout"] = timeout
    data["action"] = action_data

    notify_data: dict = {
        "on_success": notify_on_success,
        "on_failure": notify_on_failure,
    }
    if notify_title:
        notify_data["title"] = notify_title
    if max_consecutive_failures > 0:
        notify_data["max_consecutive_failures"] = max_consecutive_failures
    data["notify"] = notify_data

    dest.write_bytes(tomli_w.dumps(data).encode())

    # Generate plist and load
    plist_file = write_plist(task)
    load_plist(name)
    console.print(f"Created and loaded task '{name}'.", style="green")
    console.print(f"  TOML: {dest}")
    console.print(f"  Plist: {plist_file}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

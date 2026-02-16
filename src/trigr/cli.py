import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import tomllib
import typer
from rich.console import Console
from rich.table import Table

from trigr.config import TASKS_DIR, ensure_init, init
from trigr.models import TaskConfig
from trigr.plist import is_loaded, load_plist, plist_path, remove_plist, unload_plist, write_plist
from trigr.runner import run_task
from trigr.store import get_runs

app = typer.Typer(help="Compile task specs into launchd schedules.", no_args_is_help=True)
console = Console()


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
                "action": task.action.type,
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

        table.add_row(
            task.name,
            task.trigger.type.value,
            task.action.type,
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
    console.print(f"  Action:  {task.action.type}")
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()

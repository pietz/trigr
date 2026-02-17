# trigr

Lightweight CLI that turns TOML task specs into native macOS `launchd` schedules. No background daemon — launchd *is* the scheduler.

## Install

```bash
uv tool install trigr
```

Or from PyPI:

```bash
pipx install trigr
```

## Quick Start

```bash
# Initialize trigr (creates config dirs, captures env)
trigr init

# Create a task inline
trigr create morning-news \
  --trigger cron --hour 8 --minute 0 \
  --prompt "Summarize today's top 5 tech news in one paragraph" \
  --notify-on-success

# Or add from a TOML file
trigr add backup.toml

# Check your tasks
trigr list
```

## Task Format

Tasks are TOML files with three sections: trigger, action, and (optionally) notify.

### Script Task

```toml
name = "db-backup"
description = "Nightly database backup"

[trigger]
type = "cron"

[trigger.cron]
hour = 3
minute = 0

[action]
command = "pg_dump mydb | gzip > ~/backups/mydb-$(date +%F).sql.gz"
timeout = 600

[notify]
on_success = true
on_failure = true
```

### LLM Task

```toml
name = "morning-briefing"
description = "Daily news summary via Claude"

[trigger]
type = "cron"

[trigger.cron]
hour = 8
minute = 0

[action]
prompt = "Summarize today's top 5 tech news in one paragraph"
provider = "claude"  # also: codex, gemini

[notify]
on_success = true
```

### File Watcher

```toml
name = "lint-on-save"
description = "Run linter when source files change"

[trigger]
type = "watch"
watch_paths = ["~/projects/myapp/src"]

[action]
command = "cd ~/projects/myapp && uv run ruff check ."
working_dir = "~/projects/myapp"
```

### Interval

```toml
name = "health-check"
description = "Ping endpoint every 5 minutes"

[trigger]
type = "interval"
interval_seconds = 300

[action]
command = "curl -sf https://example.com/health || exit 1"

[notify]
on_failure = true
max_consecutive_failures = 5  # auto-disable after 5 failures in a row
```

## Triggers

| Type | Fields | Description |
|------|--------|-------------|
| `cron` | `minute`, `hour`, `day`, `weekday`, `month` | Calendar schedule (all fields optional) |
| `interval` | `interval_seconds` | Run every N seconds |
| `watch` | `watch_paths` | Run when files/directories change |

Cron weekdays: 0 = Sunday, 6 = Saturday.

## Actions

Actions are inferred from fields — no `type` field needed:

- **Script**: Set `command` to run a shell command
- **LLM**: Set `prompt` to run via an LLM provider CLI (`claude`, `codex`, or `gemini`)

Common options:

| Field | Default | Description |
|-------|---------|-------------|
| `timeout` | `300` | Kill after N seconds |
| `working_dir` | — | Working directory for the command |
| `env` | — | Extra environment variables (table) |
| `provider` | `claude` | LLM provider (only for prompt actions) |
| `model` | — | Override the provider's default model |

## Notifications

trigr sends macOS notifications via `terminal-notifier` (preferred) or `osascript` (fallback).

```toml
[notify]
on_success = false      # default
on_failure = true       # default
title = "Custom Title"  # defaults to task name
max_consecutive_failures = 5  # auto-disable after N failures (0 = never)
```

## Commands

| Command | Description |
|---------|-------------|
| `trigr init` | Create config dirs and capture environment |
| `trigr add <file.toml>` | Register task, generate plist, load into launchd |
| `trigr create <name> --trigger ... --command/--prompt ...` | Create a task inline |
| `trigr remove <name>` | Unload and delete a task |
| `trigr enable <name>` | Load task into launchd |
| `trigr disable <name>` | Unload task from launchd |
| `trigr list [--json]` | Show all tasks with status |
| `trigr show <name> [--json]` | Show full task config |
| `trigr logs [name] [-n 20] [--json]` | Show run history |
| `trigr output <name> [--stderr]` | Show last run's stdout/stderr |
| `trigr run <name>` | Execute a task immediately |
| `trigr edit <name>` | Edit task TOML in $EDITOR, re-validate on save |
| `trigr validate <file.toml>` | Check a TOML file without registering |
| `trigr refresh` | Re-capture env and regenerate all plists |
| `trigr status [--json]` | Show currently-running tasks |
| `trigr clean [--older-than 30]` | Purge old run data |

## How It Works

```
TOML task → trigr add → launchd plist → launchd fires → trigr run → execute → log + notify
```

trigr generates native `launchd` plist files in `~/Library/LaunchAgents/`. When launchd triggers a task, it calls `trigr run <name>`, which:

1. Acquires a file lock (skips if already running)
2. Runs the command or LLM prompt
3. Records the result in SQLite
4. Sends a macOS notification on success/failure

Environment variables are captured at `trigr init` time and baked into plists, so tasks run with consistent PATH and env regardless of how launchd invokes them. Run `trigr refresh` after changing your PATH or upgrading trigr.

## License

MIT

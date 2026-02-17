# trigr

Schedule LLM prompts on your Mac. Define a trigger and a prompt, and trigr handles the rest — using native `launchd` under the hood, no daemon required.

- Get a morning briefing every day at 8am
- Summarize new files dropped into a folder
- Run a shell command on a schedule and get notified if it fails

## Install

```bash
uv tool install trigr
```

Or from PyPI:

```bash
pipx install trigr
```

You'll also need at least one LLM CLI installed: [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [Codex](https://github.com/openai/codex), or [Gemini CLI](https://github.com/google-gemini/gemini-cli).

## Quick Start

```bash
# Initialize trigr (creates config dirs, captures env)
trigr init

# Morning briefing every day at 8am
trigr create morning-briefing \
  --trigger cron --hour 8 --minute 0 \
  --prompt "Give me a concise morning briefing: weather in Berlin, top 3 tech news, and any interesting AI developments from the last 24h" \
  --notify-on-success

# Describe any new file added to Downloads
trigr create describe-downloads \
  --trigger watch --watch-path ~/Downloads \
  --prompt "A new file was just added to ~/Downloads. List what's new and briefly describe what each file is." \
  --notify-on-success

# Check your tasks
trigr list
```

## Examples

### Morning Briefing

```toml
name = "morning-briefing"
description = "Daily summary to start the day"

[trigger]
type = "cron"

[trigger.cron]
hour = 8
minute = 0

[action]
prompt = "Give me a concise morning briefing: weather in Berlin, top 3 tech news, and any interesting AI developments from the last 24h"

[notify]
on_success = true
```

### Describe New Files

```toml
name = "describe-downloads"
description = "Summarize new files in Downloads"

[trigger]
type = "watch"
watch_paths = ["~/Downloads"]

[action]
prompt = "A new file was just added to ~/Downloads. List what's new and briefly describe what each file is."

[notify]
on_success = true
```

### Periodic Research

```toml
name = "ai-paper-digest"
description = "Weekly AI paper roundup"

[trigger]
type = "cron"

[trigger.cron]
hour = 18
minute = 0
weekday = 5  # Friday

[action]
prompt = "Find the 5 most interesting AI/ML papers published this week. For each, give the title, one-sentence summary, and why it matters."
provider = "gemini"

[notify]
on_success = true
```

### Script with Failure Alerts

trigr also supports plain shell commands for traditional automation:

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

## Task Format

Tasks are TOML files with three sections: **trigger**, **action**, and optionally **notify**.

### Triggers

| Type | Fields | Description |
|------|--------|-------------|
| `cron` | `minute`, `hour`, `day`, `weekday`, `month` | Calendar schedule (all fields optional) |
| `interval` | `interval_seconds` | Run every N seconds |
| `watch` | `watch_paths` | Run when files/directories change |

Cron weekdays: 0 = Sunday, 6 = Saturday.

### Actions

Actions are inferred from which field you set — no `type` needed:

- **`prompt`** — Send to an LLM provider CLI (default: `claude`)
- **`command`** — Run as a shell command

| Field | Default | Description |
|-------|---------|-------------|
| `prompt` | — | The prompt to send to the LLM |
| `command` | — | Shell command to execute |
| `provider` | `claude` | LLM provider: `claude`, `codex`, or `gemini` |
| `model` | — | Override the provider's default model |
| `timeout` | `300` | Kill after N seconds |
| `working_dir` | — | Working directory |
| `env` | — | Extra environment variables (table) |

### Notifications

trigr sends macOS notifications via `terminal-notifier` (preferred) or `osascript` (fallback). Click a notification to see the full output.

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
| `trigr add <file.toml>` | Register task from TOML file |
| `trigr create <name> --trigger ... --prompt/--command ...` | Create a task inline |
| `trigr remove <name>` | Unload and delete a task |
| `trigr enable/disable <name>` | Load/unload in launchd |
| `trigr list [--json]` | Show all tasks with status |
| `trigr show <name> [--json]` | Show full task config |
| `trigr logs [name] [-n 20] [--json]` | Show run history |
| `trigr output <name> [--stderr]` | Show last run's output |
| `trigr run <name>` | Execute a task immediately |
| `trigr edit <name>` | Edit TOML in $EDITOR, re-validate on save |
| `trigr validate <file.toml>` | Check a TOML file without registering |
| `trigr refresh` | Re-capture env and regenerate all plists |
| `trigr status [--json]` | Show currently-running tasks |
| `trigr clean [--older-than 30]` | Purge old run data |

## How It Works

```
TOML task → trigr add → launchd plist → launchd fires → trigr run → LLM/script → log + notify
```

trigr compiles your task definitions into native `launchd` plists. When a trigger fires, launchd calls `trigr run`, which executes the prompt or command, records the result in SQLite, and sends a macOS notification.

Environment is captured at `trigr init` time and baked into plists — so your LLM CLIs work reliably even when invoked by launchd. Run `trigr refresh` after PATH changes or upgrading trigr.

## License

MIT

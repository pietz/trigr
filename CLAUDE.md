# trigr

Lightweight CLI that compiles task specs (TOML) into native macOS `launchd` plists. No daemon — launchd *is* the scheduler.

## Architecture

```
TOML task → trigr add → launchd plist → launchd fires → trigr run → execute → log + notify
```

## Key Paths

- Config: `~/.config/trigr/`
- Tasks: `~/.config/trigr/tasks/*.toml`
- Logs: `~/.config/trigr/logs/`
- DB: `~/.config/trigr/history.db`
- Plists: `~/Library/LaunchAgents/com.trigr.*.plist`

## Commands

- `trigr init` — create dirs, capture env
- `trigr add <file.toml>` — register + load
- `trigr remove <name>` — unload + delete
- `trigr enable/disable <name>` — load/unload in launchd
- `trigr list [--json]` — show all tasks
- `trigr show <name> [--json]` — show config
- `trigr logs [name] [-n 20] [--json]` — run history
- `trigr run <name>` — execute immediately
- `trigr edit <name>` — edit in $EDITOR
- `trigr refresh` — re-capture env, regenerate all plists
- `trigr output <name> [--json] [--stderr]` — show last run's output
- `trigr validate <file.toml>` — check TOML without adding
- `trigr status [--json]` — show currently-running tasks
- `trigr clean [--older-than 30]` — purge old run data
- `trigr create <name> --trigger ... --command/--prompt ...` — create task inline

## Action Types

Actions are inferred from fields — no `type` field needed:
- **Script**: set `command` — runs as shell command
- **LLM**: set `prompt` — runs via an LLM provider CLI

LLM actions support `provider` (claude/codex/gemini, default: claude) and optional `model` override.

## Dev

```bash
uv sync
uv run python -m pytest  # not `uv run pytest`
uv tool install --reinstall .  # installs `trigr` globally (--reinstall to bust cache)
```

## Publishing

```bash
uv build
uv publish  # reads UV_PUBLISH_TOKEN from .env
```

PyPI token is in `.env` (gitignored).

## Notes

- Uses `plistlib` (stdlib) for plist generation
- `fcntl.flock` for run locking (skip if already running)
- SQLite for run history, osascript for notifications
- Env captured at `trigr init` time and baked into plists
- Task-level env vars via `[action.env]` in TOML
- Consecutive failure tracking: `notify.max_consecutive_failures` auto-disables tasks
- `trigr refresh` after PATH changes or `uv tool upgrade trigr`

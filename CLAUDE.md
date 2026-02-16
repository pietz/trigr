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

## Dev

```bash
uv sync
uv run pytest
uv tool install .  # installs `trigr` globally
```

## Notes

- Uses `plistlib` (stdlib) for plist generation
- `fcntl.flock` for run locking (skip if already running)
- SQLite for run history, osascript for notifications
- Env captured at `trigr init` time and baked into plists

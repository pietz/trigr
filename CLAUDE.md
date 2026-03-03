# trigr

Event system for AI CLI agents. A FastAPI server with an in-memory priority queue that delivers events into running agent sessions via long-polling.

## Architecture

```
trigr.toml → trigr serve → FastAPI + APScheduler
                              ├── POST /emit    (push events)
                              ├── GET  /next    (long-poll, blocks until event)
                              └── GET  /status  (server info)

Agent workflow:
  trigr watch  ──→  GET /next  ──→  blocks  ──→  prints message  ──→  exits
  trigr emit   ──→  POST /emit ──→  queued  ──→  delivered to next watcher
```

## Key Files

- `src/trigr/models.py` — Pydantic models: ServerConfig, PollerConfig, CronConfig, TrigrConfig, Event, EmitRequest
- `src/trigr/config.py` — TOML loading, find_config()
- `src/trigr/server.py` — FastAPI app, priority queue, APScheduler integration
- `src/trigr/cli.py` — Typer CLI: init, serve, stop, watch, emit, run, list, add, remove, status
- `trigr.toml` — project-local config (server settings, pollers, crons)
- `.trigr.pid` — PID file for detached server (project-local)

## Commands

- `trigr init [--token]` — create trigr.toml in cwd (--token generates a random auth token)
- `trigr serve [-f] [--verbose] [--no-auth]` — start server (detached by default, -f for foreground)
- `trigr stop [--port]` — stop the detached server
- `trigr watch [--timeout] [--verbose]` — long-poll for next event, print message, exit (0 = wait forever)
- `trigr emit [message] [--delay 48h]` — push event to queue (reads stdin if no message arg)
- `trigr run <name>` — run a poller/cron command once and show its output (no server needed)
- `trigr list` — list configured pollers and crons from trigr.toml
- `trigr add <name> --command "..." (--interval N | --cron "...")` — add poller/cron to trigr.toml
- `trigr remove <name>` — remove poller/cron from trigr.toml
- `trigr status` — show server state (read-only, does not auto-start)

## Dev

```bash
uv sync
uv run python -m pytest  # not `uv run pytest`
uv tool install --reinstall .  # install trigr globally
```

## Publishing

```bash
uv build
uv publish  # reads UV_PUBLISH_TOKEN from .env
```

PyPI token is in `.env` (gitignored).

## Notes

- Priority queue only contains ready-to-deliver events; delayed events use asyncio tasks that sleep until fire_at
- Pollers run commands via async subprocess, stdout becomes the event message
- Pollers deduplicate: identical consecutive output is silently skipped (resets on server restart)
- `trigr status` is read-only — does not auto-start the server
- Server auto-starts when using `trigr watch` or `trigr emit`
- `--verbose` on `watch` is forwarded to the auto-started server
- Stale PID files are cleaned up automatically when the process is no longer alive
- PID file (.trigr.pid) and log file (.trigr.log) are project-local
- Server stderr goes to .trigr.log for debugging startup failures
- Changes to trigr.toml (add/remove) require server restart to take effect
- Default port: 9374
- All datetimes are UTC internally
- `trigr emit` reads from stdin when no message argument is given (`echo "msg" | trigr emit`)
- Auth token: set `token = "..."` in trigr.toml `[server]` section for Bearer auth on all endpoints
- Non-localhost binding requires a token or `--no-auth` flag on `trigr serve`
- Version is single source of truth in pyproject.toml (no `__version__` in code)
- Skill file at `skills/trigr/SKILL.md` — keep in sync with CLI changes

# trigr

Event system for AI CLI agents. A FastAPI server with an in-memory priority queue that delivers events into running agent sessions via long-polling.

## Architecture

```
trigr.toml → trigr serve → FastAPI + APScheduler
                              ├── POST /emit    (push events)
                              ├── GET  /next    (long-poll, blocks until event)
                              └── GET  /status  (server info)

Agent workflow:
  trigr watch  ──→  GET /next  ──→  blocks  ──→  prints JSON  ──→  exits
  trigr emit   ──→  POST /emit ──→  queued  ──→  delivered to next watcher
```

## Key Files

- `src/trigr/models.py` — Pydantic models: ServerConfig, PollerConfig, CronConfig, TrigrConfig, Event, EmitRequest
- `src/trigr/config.py` — TOML loading, find_config(), server_url()
- `src/trigr/server.py` — FastAPI app, priority queue, APScheduler integration
- `src/trigr/cli.py` — Typer CLI: init, serve, watch, emit, add, status
- `trigr.toml` — project-local config (server settings, pollers, crons)
- `.trigr.pid` — PID file for detached server (project-local)

## Commands

- `trigr init` — create trigr.toml in cwd
- `trigr serve [-f]` — start server (detached by default, -f for foreground)
- `trigr watch [--timeout 300]` — long-poll for next event, print JSON, exit
- `trigr emit <type> [--data '{}'] [--delay 48h]` — push event to queue
- `trigr add <name> --command "..." (--interval N | --cron "...")` — add poller/cron to trigr.toml
- `trigr status` — show server state

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

- Priority queue sorts by (fire_at, sequence_number) for FIFO within same timestamp
- Pollers run commands via subprocess in executor threads, parse stdout as JSON
- Server auto-starts when using `trigr watch` or `trigr emit`
- PID file is project-local (.trigr.pid), supporting multiple servers on different ports
- Default port: 9374

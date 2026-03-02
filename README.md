# trigr

Event system for AI CLI agents. Run `trigr watch` inside your agent session to receive events — from other terminals, scheduled pollers, or cron jobs.

- Deliver events *into* a running Claude Code / Codex / Gemini session
- Schedule pollers (interval) and cron jobs that produce events
- Simple long-polling: `trigr watch` blocks, prints JSON, exits

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
# Create config in your project
trigr init

# Terminal 1: watch for events (auto-starts server)
trigr watch

# Terminal 2: emit an event
trigr emit hello --data '{"msg": "world"}'
# → Terminal 1 prints the event JSON and exits
```

## Use with AI Agents

The key insight: `trigr watch` is a blocking call that prints JSON and exits — perfect for background tasks in agent sessions.

```bash
# In Claude Code, run as a background task:
trigr watch --timeout 3600

# When an event arrives, the background task completes
# and the agent receives the event data as a notification
```

From another terminal (or a script, webhook handler, etc.):

```bash
trigr emit code_review --data '{"pr": 42, "repo": "myapp"}'
```

## trigr.toml

Project-local configuration file. Created by `trigr init`.

```toml
[server]
host = "127.0.0.1"
port = 9374

# Pollers run on an interval, stdout parsed as JSON → queued as event
[pollers.check-inbox]
interval = 300
command = "python check_mail.py"

# Cron jobs use 5-field cron expressions
[crons.morning-sync]
cron = "0 9 * * *"
command = "echo '{\"type\": \"morning\", \"data\": {}}'"
```

### Poller Output Format

Poller commands should print JSON to stdout. If the JSON has a `type` field, it's used as the event type. Otherwise, the event type defaults to `poller.<name>`.

```bash
# Simple poller command
echo '{"type": "new_email", "data": {"from": "alice@example.com", "subject": "Hello"}}'
```

## Commands

| Command | Description |
|---------|-------------|
| `trigr init` | Create `trigr.toml` in the current directory |
| `trigr serve [-f]` | Start server (detached by default, `-f` foreground) |
| `trigr watch [--timeout 300]` | Block until event, print JSON, exit |
| `trigr emit <type> [--data '{}'] [--delay 10s]` | Push event to queue |
| `trigr add <name> -c "cmd" (--interval N \| --cron "...")` | Add poller/cron to config |
| `trigr status` | Show server state |

### Delayed Events

```bash
# Deliver event in 2 hours
trigr emit reminder --data '{"task": "review PR"}' --delay 2h

# Supported units: s (seconds), m (minutes), h (hours), d (days)
```

## How It Works

```
trigr serve → FastAPI server + APScheduler
                ├── POST /emit    (push events to priority queue)
                ├── GET  /next    (long-poll, blocks until event ready)
                └── GET  /status  (queue depth, registered jobs)
```

Events are stored in an in-memory priority queue sorted by delivery time. `GET /next` blocks until an event is available whose `fire_at` time has passed, then returns it as JSON.

The server auto-starts when you run `trigr watch` or `trigr emit`. A `.trigr.pid` file is written next to `trigr.toml`, so multiple projects can run their own server on different ports.

## License

MIT

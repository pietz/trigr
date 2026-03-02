# trigr

AI CLI coding agents (Claude Code, Codex, Gemini CLI) are reactive — they only work when a human types a message. They have no native event system, no triggers, no way to react to external events autonomously.

**trigr** fixes that. It's a lightweight event system that delivers events *into* a running agent session. The agent calls `trigr watch`, goes to sleep, and wakes up when something happens.

```
Agent runs trigr watch (background task or blocking)
    → blocks until event
    → event arrives → prints JSON → exits
    → agent wakes up, processes event
    → agent runs trigr watch again
    → "asleep" until next event
```

One tool. One pattern. Works with any agent.

## Install

```bash
uv tool install trigr
```

## Quick Start

```bash
# Initialize trigr in your project
trigr init

# Terminal 1: watch for events (auto-starts server)
trigr watch

# Terminal 2: send an event
trigr emit hello --data '{"msg": "world"}'
# → Terminal 1 prints the event JSON and exits
```

## Agent Integration

### Claude Code

`trigr watch` runs as a background task — the agent can chat with the user while waiting for events. When an event arrives, the background task exits and the agent gets notified.

```bash
# In a Claude Code skill or agent instruction:
# "Run trigr watch as a background task. When it completes, process the event and restart."
trigr watch --timeout 3600
```

### Codex CLI / Gemini CLI

`trigr watch` runs as a blocking call. The agent waits for the next event, processes it, and restarts the loop.

| Agent | How trigr watch runs | Background chatting? |
|-------|---------------------|---------------------|
| Claude Code | Background task | Yes |
| Codex CLI | Blocking call | No (not needed) |
| Gemini CLI | Blocking call | No |

## Event Sources

trigr supports three ways to produce events:

### 1. Manual / Programmatic

Anything can POST events — other terminals, scripts, webhooks, other agents:

```bash
trigr emit code_review --data '{"pr": 42, "repo": "myapp"}'
```

### 2. Pollers

Shell commands that run on an interval. If stdout is non-empty, it becomes an event:

```toml
[pollers.check-inbox]
interval = 60
command = "python check_mail.py"
```

### 3. Cron Jobs

Shell commands on a cron schedule:

```toml
[crons.daily-summary]
cron = "0 9 * * *"
command = "python daily_report.py"
```

Pollers and cron commands are language-agnostic. Write a script in any language that prints JSON to stdout. trigr runs it on schedule.

### Delayed Events

The agent can schedule its own future events — perfect for follow-ups:

```bash
# "Follow up in 48 hours if no response"
trigr emit followup --data '{"candidate": "C-4821"}' --delay 48h

# Supported units: s (seconds), m (minutes), h (hours), d (days)
```

## trigr.toml

Project-local configuration. Created by `trigr init`.

```toml
[server]
host = "127.0.0.1"
port = 9374

[pollers.check-inbox]
interval = 60
command = "python check_mail.py"

[crons.morning-sync]
cron = "0 9 * * *"
command = "echo '{\"type\": \"morning\"}'"
```

Add jobs from the CLI:

```bash
trigr add inbox-check --interval 60 --command "python check_mail.py"
trigr add daily-report --cron "0 9 * * *" --command "python report.py"
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

## How It Works

```
trigr serve → FastAPI server + APScheduler
                ├── POST /emit    (push events to priority queue)
                ├── GET  /next    (long-poll, blocks until event ready)
                └── GET  /status  (queue depth, registered jobs)
```

Events sit in an in-memory priority queue sorted by delivery time. `GET /next` blocks until an event whose `fire_at` has passed, then returns it as JSON.

The server auto-starts when you run `trigr watch` or `trigr emit`. A `.trigr.pid` file lives next to `trigr.toml`, so multiple projects can run independent servers on different ports.

## Poller Output Format

Poller commands should print JSON to stdout. If the JSON has a `type` field, it's used as the event type. Otherwise it defaults to `poller.<name>`.

```bash
# Poller script example
echo '{"type": "new_email", "data": {"from": "jane@example.com", "subject": "Re: Role"}}'
```

If stdout is empty, no event is created. This lets pollers silently skip cycles when nothing is new.

## License

MIT

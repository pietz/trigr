---
name: trigr
description: Use when the user wants the agent to run autonomously, react to external events, schedule recurring tasks, or wait for messages. trigr is an event system that lets you go to sleep and wake up when something happens — a message arrives, a poller detects a change, or a cron job fires.
---

# trigr

trigr is an event system that makes you autonomous. You can wait for external events, run tasks on a schedule, and react to changes — all from within your session.

## Core Loop

1. Run `trigr watch` as a background task
2. Go about your business or wait
3. When a message arrives, the background task prints it and exits
4. Process the message
5. Run `trigr watch` again

```bash
# Start watching (auto-creates config and starts server if needed)
trigr watch --timeout 3600
```

## Receiving Messages

`trigr watch` blocks until a message arrives, prints it to stdout, and exits. Run it as a background task so you get notified when something happens.

If no message arrives within the timeout (default 300s), it exits with code 1.

## Sending Messages

From your session, another terminal, or any script:

```bash
trigr emit "New PR opened — please review"
```

You can delay delivery:

```bash
trigr emit "Follow up with the candidate" --delay 48h
```

Units: `s` (seconds), `m` (minutes), `h` (hours), `d` (days).

## Adding Scheduled Jobs

### Cron Jobs (run at specific times)

```bash
# Static message
trigr add daily-standup --cron "0 9 * * 1-5" --message "Run the daily standup routine"

# Dynamic: run a command, its stdout becomes the message
trigr add daily-news --cron "0 9 * * *" --command "python daily_news.py"

# Both: message first, then command output appended
trigr add report --cron "0 18 * * 5" --message "Weekly summary:" --command "python weekly_stats.py"
```

### Pollers (run at regular intervals)

```bash
trigr add check-inbox --interval 300 --command "./check_email.sh"
```

If a command prints nothing, no message is created. Pollers silently skip cycles when nothing is new.

## Commands

| Command | What it does |
|---------|-------------|
| `trigr watch [--timeout 300]` | Block until message, print it, exit |
| `trigr emit "msg" [--delay 10s]` | Send a message |
| `trigr add <name> --cron "..." --message "..."` | Add a cron job |
| `trigr add <name> --interval N --command "..."` | Add a poller |
| `trigr status` | Show server state and scheduled jobs |
| `trigr init` | Create trigr.toml (auto-created on first use) |
| `trigr serve [-f]` | Start server manually |

All commands accept `--port N` to override the default port (9374).

## Configuration

`trigr.toml` is auto-created in the working directory on first use. You can also define jobs directly in it:

```toml
[server]
host = "127.0.0.1"
port = 9374

[pollers.check-inbox]
interval = 60
command = "./check_mail.sh"

[crons.daily-report]
cron = "0 9 * * *"
command = "echo 'time for the daily report'"
```

## Tips

- The server auto-starts on `trigr watch` or `trigr emit` — no manual setup needed
- Use `trigr status` to see queue depth and scheduled jobs
- Multiple projects can run independent servers on different ports
- Pollers should manage their own state (track what they've already seen)
- Use `--delay` on `trigr emit` for self-scheduled follow-ups

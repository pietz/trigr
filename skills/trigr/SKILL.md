---
name: trigr
description: Use when the user wants the agent to run autonomously, react to external events, schedule recurring tasks, or wait for messages. trigr is an event system that lets you go to sleep and wake up when something happens — a message arrives, a poller detects a change, or a cron job fires.
---

# trigr

trigr is an event system that makes you (the AI agent) autonomous. You can wait for external events, run tasks on a schedule, and react to changes — all from within your session.

## Install

```bash
uv tool install trigr
```

## Why This Matters

You are a powerful agent, but you only act when prompted. Without trigr, you start when a human types a message and stop when you're done. trigr changes this: it lets you go to sleep and be woken up by events — turning you from a reactive tool into a proactive system that runs continuously.

## Event Sources

trigr supports three ways to wake you up:

**Emit** — An external entity (a human, another agent, a script) sends you a message from another terminal. This is the simplest trigger: someone runs `trigr emit "do something"` and you wake up with that message.

**Cron** — A scheduled job fires at a specific time. You wake up on schedule regardless of whether anything changed. Example: `trigr add morning-briefing --cron "0 9 * * 1-5" --message "Summarize the top news from the past 24 hours"`.

**Poller** — A script runs at regular intervals, but you only wake up if the script produces output. If the script prints nothing, you stay asleep. This is the key difference from cron: pollers are conditional. Use pollers when you want to react to changes (new emails, updated files, status changes) without waking up unnecessarily every cycle. Example: `trigr add check-inbox --interval 300 --command "./check_email.sh"` — the script checks for new emails and prints their subjects only when something arrived.

## The Loop

This is how you operate with trigr:

0. **Set up your triggers** — configure crons, pollers, or rely on external emits
1. **Run `trigr watch`** — you go to sleep, producing no output, waiting
2. **An event arrives** — `watch` prints the event message to stdout and exits
3. **You wake up, process the event**, do whatever work is needed
4. **Run `trigr watch` again** — back to sleep, loop restarts at step 1

```bash
trigr watch              # sleep until event (waits forever by default)
trigr watch --timeout N  # sleep up to N seconds (exits code 1 on timeout)
```

## Sending Messages

From another terminal, a script, or your own session:

```bash
trigr emit "New PR opened — please review"
echo "deployment failed" | trigr emit       # pipe from stdin
trigr emit "Follow up" --delay 48h          # delayed delivery (s/m/h/d)
```

## Configuring Triggers

### Cron jobs

```bash
trigr add daily-standup --cron "0 9 * * 1-5" --message "Run the daily standup routine"
trigr add daily-news --cron "0 9 * * *" --command "python daily_news.py"
trigr add report --cron "0 18 * * 5" --message "Weekly summary:" --command "python weekly_stats.py"
```

### Pollers

```bash
trigr add check-inbox --interval 300 --command "./check_email.sh"
```

The script runs every N seconds. If it prints output → you get a message. If it prints nothing → you stay asleep. Identical consecutive outputs are automatically deduplicated.

### Configuration file

Triggers can also be defined in `trigr.toml` (auto-created on first use):

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

After changing `trigr.toml`, restart the server for changes to take effect.

## Commands

| Command | What it does |
|---------|-------------|
| `trigr watch [--timeout 0] [--verbose]` | Sleep until event, print it, exit (0 = forever) |
| `trigr emit ["msg"] [--delay 10s]` | Send a message (reads stdin if no arg) |
| `trigr add <name> --cron/--interval ...` | Add a cron job or poller |
| `trigr remove <name>` | Remove a cron job or poller |
| `trigr run <name>` | Test a poller/cron command once without the server |
| `trigr list` | List configured pollers and crons |
| `trigr status` | Show server state, queue depth, and scheduled jobs |
| `trigr stop` | Stop the server |
| `trigr init [--token]` | Create trigr.toml |
| `trigr serve [-f] [--verbose] [--no-auth]` | Start server manually |

All commands accept `--port N` to override the default port (9374).

## Tips

- The server auto-starts on `trigr watch` or `trigr emit` — no manual setup needed
- Use `trigr run <name>` to test a poller/cron before relying on it
- Poller commands time out after 30 seconds — keep scripts fast
- Use `--verbose` on `watch` or `serve` for debug logging (→ `.trigr.log`)
- Multiple projects can run independent servers on different ports
- Use `--delay` on `trigr emit` to schedule self-reminders

# trigr

**Make any AI coding agent autonomous.**

AI coding agents like Claude Code are **reactive**. They only do something when prompted.

OpenClaw changes that by running agents in the background, but it's a full platform you have to self-host, with [known security risks](https://www.kaspersky.com/blog/openclaw-vulnerabilities-exposed/55263/) around exposed instances and malicious plugins.

**trigr** bridges this gap through a simple trigger system. It lets the agent wait for events to autonomously run tasks when something happens. Once it's done, it goes back to sleep until the next event.

## Quickstart

1. The agent starts trigr as a background command.

```bash
uvx trigr watch
# trigr server runs on port 9374 (default)
```

2. An external event is emitted.

```bash
uvx trigr emit "New GitHub issue opened: #1337 - Please triage."
```

3. The agent wakes up and runs the task.

## Install

```bash
uv tool install trigr
```

## Triggers

We currently support 3 types of triggers: messages, CRON jobs, and pollers.

## Messages (External Triggers)

You can send messages from another terminal, script, or the agent itself.

```bash
trigr emit "New GitHub issue opened: #1337 - Please triage."
```

You can delay messages too, if you want the agent to wait before acting.

```bash
trigr emit "Check if the deployment ran successfully and fix if needed." --delay 20m
```

## CRON Jobs (Scheduled Triggers)

CRON jobs run at a specific time schedule.

```bash
trigr add daily-news --cron "0 9 * * *" --message "Retrieve the top 5 trending hacker news stories."
```

You can also prompt the agent to run a command and use its output as the message.

```bash
trigr add daily-news --cron "0 9 * * *" --command "python daily_news.py"
```

Instead of using the CLI, you can also define cron jobs in `trigr.toml`.

```toml
[crons.daily-report]
cron = "0 9 * * *"
command = "echo 'time for the daily report'"
```

## Pollers (Interval Triggers)

Pollers run at regular intervals, like every 5 minutes to check your email.

```bash
trigr add email-response --interval 300 --command "./check_email.sh"
```

If a command prints nothing, no message is created. Pollers silently skip cycles when nothing is new.

```toml
[pollers.check-inbox]
interval = 60
command = "./check_mail.sh"
```

## Commands

| Command | What it does |
|---------|-------------|
| `trigr watch [--timeout 300]` | Block until message, print it, exit |
| `trigr emit "msg" [--delay 10s]` | Send a message |
| `trigr add <name> --interval N -m "msg"` | Add a poller with a static message |
| `trigr add <name> --cron "..." -c "cmd"` | Add a cron job with a command |
| `trigr status` | Show server state |
| `trigr init` | Create `trigr.toml` (auto-created on first use) |
| `trigr serve [-f]` | Start server manually |

## Agent Compatibility

| Agent | How `trigr watch` runs | Chat while waiting? |
|-------|----------------------|---------------------|
| Claude Code | Background task | Yes |
| Codex CLI | Blocking call | No |
| Gemini CLI | Blocking call | No |

## License

MIT

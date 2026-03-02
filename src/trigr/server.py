import asyncio
import logging
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from trigr.config import load_config
from trigr.models import EmitRequest, Event, TrigrConfig

logger = logging.getLogger("trigr.server")

# Global state
_queue: asyncio.PriorityQueue[tuple[datetime, int, Event]] = asyncio.PriorityQueue()
_seq = 0
_scheduler: AsyncIOScheduler | None = None
_config: TrigrConfig = TrigrConfig()


def _next_seq() -> int:
    global _seq
    _seq += 1
    return _seq


async def enqueue(event: Event, fire_at: datetime | None = None) -> None:
    """Push an event onto the priority queue."""
    when = fire_at or event.timestamp
    _queue.put_nowait((when, _next_seq(), event))


def _parse_cron(expr: str) -> CronTrigger:
    """Parse a 5-field cron expression into an APScheduler CronTrigger."""
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Expected 5-field cron expression, got {len(parts)} fields: {expr!r}")
    minute, hour, day, month, day_of_week = parts
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
    )


def _run_poller_command(name: str, command: str) -> None:
    """Run a poller command synchronously and enqueue its output."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30,
        )
        stdout = result.stdout.strip()
        if not stdout:
            return

        event = Event(message=stdout)
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(
            lambda e=event: _queue.put_nowait((e.timestamp, _next_seq(), e)),
        )
    except subprocess.TimeoutExpired:
        logger.warning("Poller %s timed out", name)
    except Exception:
        logger.exception("Poller %s failed", name)


def _register_jobs(scheduler: AsyncIOScheduler, config: TrigrConfig) -> None:
    """Register pollers and cron jobs with the scheduler."""
    for name, poller in config.pollers.items():
        scheduler.add_job(
            _run_poller_command,
            trigger=IntervalTrigger(seconds=poller.interval),
            args=[name, poller.command],
            id=f"poller.{name}",
            name=f"poller.{name}",
        )
        logger.info("Registered poller %r (every %ds)", name, poller.interval)

    for name, cron in config.crons.items():
        scheduler.add_job(
            _run_poller_command,
            trigger=_parse_cron(cron.cron),
            args=[name, cron.command],
            id=f"cron.{name}",
            name=f"cron.{name}",
        )
        logger.info("Registered cron %r (%s)", name, cron.cron)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _scheduler, _config
    _config = load_config()
    _scheduler = AsyncIOScheduler()
    _register_jobs(_scheduler, _config)
    _scheduler.start()
    logger.info("trigr server started on %s:%d", _config.server.host, _config.server.port)
    yield
    _scheduler.shutdown(wait=False)
    logger.info("trigr server stopped")


app = FastAPI(title="trigr", lifespan=lifespan)


@app.post("/emit")
async def emit(req: EmitRequest) -> dict:
    event = Event(message=req.message)
    await enqueue(event, fire_at=req.fire_at)
    return {"status": "queued"}


@app.get("/next")
async def next_event(timeout: int = 300) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return {"status": "timeout"}
        try:
            fire_at, seq, event = await asyncio.wait_for(
                _queue.get(), timeout=min(remaining, 1.0),
            )
        except asyncio.TimeoutError:
            continue

        # Check if event should fire yet
        now = datetime.now()
        if fire_at > now:
            # Put it back and wait
            _queue.put_nowait((fire_at, seq, event))
            wait_secs = min((fire_at - now).total_seconds(), remaining)
            if wait_secs > 0:
                await asyncio.sleep(min(wait_secs, 1.0))
            continue

        return event.model_dump(mode="json")


@app.get("/status")
async def status() -> dict:
    jobs = []
    if _scheduler:
        for job in _scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
            })
    return {
        "status": "running",
        "queue_depth": _queue.qsize(),
        "pollers": len(_config.pollers),
        "crons": len(_config.crons),
        "jobs": jobs,
    }

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from trigr.config import load_config
from trigr.models import EmitRequest, Event, TrigrConfig

logger = logging.getLogger("trigr.server")

# Global state
_queue: asyncio.PriorityQueue[tuple[datetime, int, Event]] = asyncio.PriorityQueue()
_seq = 0
_scheduler: AsyncIOScheduler | None = None
_config: TrigrConfig = TrigrConfig()
_delayed_tasks: set[asyncio.Task] = set()
_last_poller_output: dict[str, str] = {}


def _next_seq() -> int:
    global _seq
    _seq += 1
    return _seq


async def _deliver_delayed(event: Event, fire_at: datetime, seq: int) -> None:
    """Sleep until fire_at, then put event into the ready queue."""
    delay = (fire_at - datetime.now(tz=timezone.utc)).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    _queue.put_nowait((fire_at, seq, event))


async def enqueue(event: Event, fire_at: datetime | None = None) -> None:
    """Push an event onto the priority queue."""
    when = fire_at or event.timestamp
    seq = _next_seq()
    if when > datetime.now(tz=timezone.utc):
        task = asyncio.create_task(_deliver_delayed(event, when, seq))
        _delayed_tasks.add(task)
        task.add_done_callback(_delayed_tasks.discard)
    else:
        _queue.put_nowait((when, seq, event))


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


async def _run_poller_command(name: str, command: str) -> None:
    """Run a poller command asynchronously and enqueue its output."""
    try:
        logger.debug("Poller %s running: %s", name, command)
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("Poller %s timed out", name)
            return

        if stderr:
            logger.debug("Poller %s stderr: %s", name, stderr.decode().strip())

        output = stdout.decode().strip()
        logger.debug("Poller %s output: %d chars", name, len(output))
        if not output:
            logger.debug("Poller %s: empty output, skipping", name)
            return

        # Deduplicate: skip if output is identical to last run
        if _last_poller_output.get(name) == output:
            logger.debug("Poller %s: deduplicated, skipping", name)
            return
        _last_poller_output[name] = output

        event = Event(message=output)
        await enqueue(event)
        logger.debug("Poller %s: event enqueued", name)
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
    for task in _delayed_tasks:
        task.cancel()
    _delayed_tasks.clear()
    _last_poller_output.clear()
    logger.info("trigr server stopped")


app = FastAPI(title="trigr", lifespan=lifespan)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Check Bearer token when server has a token configured."""
    token = _config.server.token
    if token:
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {token}":
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.post("/emit")
async def emit(req: EmitRequest) -> dict:
    event = Event(message=req.message)
    await enqueue(event, fire_at=req.fire_at)
    return {"status": "queued"}


@app.get("/next")
async def next_event(timeout: int = 0) -> dict:
    try:
        if timeout <= 0:
            fire_at, seq, event = await _queue.get()
        else:
            fire_at, seq, event = await asyncio.wait_for(_queue.get(), timeout=timeout)
        return event.model_dump(mode="json")
    except asyncio.TimeoutError:
        return {"status": "timeout"}


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

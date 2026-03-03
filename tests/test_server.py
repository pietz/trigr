import asyncio
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from trigr.server import app


@pytest_asyncio.fixture
async def client():
    import trigr.server as srv

    # Reset all global state
    srv._queue = asyncio.PriorityQueue()
    srv._seq = 0
    srv._last_poller_output.clear()
    srv._config.server.token = None
    for task in srv._delayed_tasks:
        task.cancel()
    if srv._delayed_tasks:
        await asyncio.gather(*srv._delayed_tasks, return_exceptions=True)
    srv._delayed_tasks.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    # Teardown: reset everything again to avoid leaking into next test
    srv._config.server.token = None
    srv._last_poller_output.clear()
    tasks = list(srv._delayed_tasks)
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    srv._delayed_tasks.clear()


async def test_emit_then_next(client: AsyncClient) -> None:
    resp = await client.post("/emit", json={"message": "hello world"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"

    resp = await client.get("/next", params={"timeout": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "hello world"


async def test_next_timeout(client: AsyncClient) -> None:
    resp = await client.get("/next", params={"timeout": 1})
    assert resp.status_code == 200
    assert resp.json()["status"] == "timeout"


async def test_delayed_event_not_returned_early(client: AsyncClient) -> None:
    fire_at = (datetime.now(tz=timezone.utc) + timedelta(seconds=3)).isoformat()
    await client.post("/emit", json={"message": "delayed", "fire_at": fire_at})

    resp = await client.get("/next", params={"timeout": 1})
    assert resp.json()["status"] == "timeout"


async def test_delayed_event_returned_after_fire_at(client: AsyncClient) -> None:
    fire_at = (datetime.now(tz=timezone.utc) + timedelta(seconds=1)).isoformat()
    await client.post("/emit", json={"message": "future msg", "fire_at": fire_at})

    resp = await client.get("/next", params={"timeout": 5})
    body = resp.json()
    assert body["message"] == "future msg"


async def test_status(client: AsyncClient) -> None:
    resp = await client.get("/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert "queue_depth" in body
    assert "pollers" in body
    assert "crons" in body
    assert "jobs" in body


async def test_poller_dedup() -> None:
    """Poller dedup skips duplicate output."""
    import trigr.server as srv

    # Full state reset for standalone test
    srv._last_poller_output.clear()
    srv._queue = asyncio.PriorityQueue()
    srv._seq = 0
    for task in srv._delayed_tasks:
        task.cancel()
    if srv._delayed_tasks:
        await asyncio.gather(*srv._delayed_tasks, return_exceptions=True)
    srv._delayed_tasks.clear()

    # First run: should enqueue
    await srv._run_poller_command("test_poller", "echo hello")
    assert srv._queue.qsize() == 1

    # Second run with same output: should skip
    await srv._run_poller_command("test_poller", "echo hello")
    assert srv._queue.qsize() == 1

    # Third run with different output: should enqueue
    await srv._run_poller_command("test_poller", "echo world")
    assert srv._queue.qsize() == 2


async def test_auth_middleware_rejects_without_token(client: AsyncClient) -> None:
    """When token is set, requests without auth are rejected."""
    import trigr.server as srv
    srv._config.server.token = "secret123"

    resp = await client.get("/status")
    assert resp.status_code == 401


async def test_auth_middleware_rejects_wrong_token(client: AsyncClient) -> None:
    """When token is set, requests with wrong token are rejected."""
    import trigr.server as srv
    srv._config.server.token = "secret123"

    resp = await client.get("/status", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401


async def test_auth_middleware_accepts_with_token(client: AsyncClient) -> None:
    """When token is set, requests with correct auth succeed."""
    import trigr.server as srv
    srv._config.server.token = "secret123"

    resp = await client.get("/status", headers={"Authorization": "Bearer secret123"})
    assert resp.status_code == 200


async def test_auth_middleware_no_token_configured(client: AsyncClient) -> None:
    """When no token is configured, all requests are allowed."""
    resp = await client.get("/status")
    assert resp.status_code == 200

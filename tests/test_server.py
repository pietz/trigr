from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from trigr.server import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_emit_then_next(client: AsyncClient) -> None:
    resp = await client.post("/emit", json={"type": "test", "data": {"msg": "hello"}})
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"

    resp = await client.get("/next", params={"timeout": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "test"
    assert body["data"]["msg"] == "hello"


@pytest.mark.asyncio
async def test_next_timeout(client: AsyncClient) -> None:
    resp = await client.get("/next", params={"timeout": 1})
    assert resp.status_code == 200
    assert resp.json()["status"] == "timeout"


@pytest.mark.asyncio
async def test_delayed_event_not_returned_early(client: AsyncClient) -> None:
    fire_at = (datetime.now() + timedelta(seconds=3)).isoformat()
    await client.post("/emit", json={"type": "delayed", "fire_at": fire_at})

    # With a 1s timeout, the delayed event should not be returned
    resp = await client.get("/next", params={"timeout": 1})
    assert resp.json()["status"] == "timeout"


@pytest.mark.asyncio
async def test_delayed_event_returned_after_fire_at(client: AsyncClient) -> None:
    fire_at = (datetime.now() + timedelta(seconds=1)).isoformat()
    await client.post("/emit", json={"type": "delayed", "data": {"v": 1}, "fire_at": fire_at})

    resp = await client.get("/next", params={"timeout": 5})
    body = resp.json()
    assert body["type"] == "delayed"
    assert body["data"]["v"] == 1


@pytest.mark.asyncio
async def test_status(client: AsyncClient) -> None:
    resp = await client.get("/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert "queue_depth" in body
    assert "pollers" in body
    assert "crons" in body
    assert "jobs" in body


@pytest.mark.asyncio
async def test_emit_with_source(client: AsyncClient) -> None:
    await client.post("/emit", json={"type": "src_test", "source": "my-agent"})
    resp = await client.get("/next", params={"timeout": 5})
    assert resp.json()["source"] == "my-agent"

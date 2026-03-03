from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 9374
    token: str | None = None


class PollerConfig(BaseModel):
    interval: int  # seconds
    command: str


class CronConfig(BaseModel):
    cron: str  # 5-field cron expression
    command: str


class TrigrConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    pollers: dict[str, PollerConfig] = {}
    crons: dict[str, CronConfig] = {}


class Event(BaseModel):
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class EmitRequest(BaseModel):
    message: str
    fire_at: datetime | None = None

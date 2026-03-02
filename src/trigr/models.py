from datetime import datetime

from pydantic import BaseModel


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 9374


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
    type: str
    source: str = ""
    data: dict = {}
    timestamp: datetime = None  # type: ignore[assignment]

    def __init__(self, **kwargs: object) -> None:
        if "timestamp" not in kwargs or kwargs["timestamp"] is None:
            kwargs["timestamp"] = datetime.now()
        super().__init__(**kwargs)


class EmitRequest(BaseModel):
    type: str
    data: dict = {}
    source: str = ""
    fire_at: datetime | None = None

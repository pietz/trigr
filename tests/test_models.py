from datetime import datetime

import pytest
from pydantic import ValidationError

from trigr.models import (
    CronConfig,
    EmitRequest,
    Event,
    PollerConfig,
    ServerConfig,
    TrigrConfig,
)


class TestServerConfig:
    def test_defaults(self) -> None:
        cfg = ServerConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 9374

    def test_custom(self) -> None:
        cfg = ServerConfig(host="0.0.0.0", port=8080)
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8080


class TestPollerConfig:
    def test_valid(self) -> None:
        p = PollerConfig(interval=60, command="echo hi")
        assert p.interval == 60
        assert p.command == "echo hi"

    def test_missing_interval(self) -> None:
        with pytest.raises(ValidationError):
            PollerConfig(command="echo hi")  # type: ignore[call-arg]

    def test_missing_command(self) -> None:
        with pytest.raises(ValidationError):
            PollerConfig(interval=60)  # type: ignore[call-arg]


class TestCronConfig:
    def test_valid(self) -> None:
        c = CronConfig(cron="*/5 * * * *", command="date")
        assert c.cron == "*/5 * * * *"

    def test_missing_cron(self) -> None:
        with pytest.raises(ValidationError):
            CronConfig(command="date")  # type: ignore[call-arg]


class TestTrigrConfig:
    def test_defaults(self) -> None:
        cfg = TrigrConfig()
        assert cfg.server.port == 9374
        assert cfg.pollers == {}
        assert cfg.crons == {}

    def test_with_pollers_and_crons(self) -> None:
        cfg = TrigrConfig(
            pollers={"check": PollerConfig(interval=30, command="echo ok")},
            crons={"daily": CronConfig(cron="0 9 * * *", command="date")},
        )
        assert "check" in cfg.pollers
        assert cfg.pollers["check"].interval == 30
        assert "daily" in cfg.crons


class TestEvent:
    def test_defaults(self) -> None:
        e = Event(message="hello")
        assert e.message == "hello"
        assert isinstance(e.timestamp, datetime)

    def test_custom_timestamp(self) -> None:
        ts = datetime(2025, 1, 1, 12, 0)
        e = Event(message="hello", timestamp=ts)
        assert e.timestamp == ts


class TestEmitRequest:
    def test_minimal(self) -> None:
        r = EmitRequest(message="ping")
        assert r.message == "ping"
        assert r.fire_at is None

    def test_with_fire_at(self) -> None:
        ts = datetime(2025, 6, 1, 12, 0)
        r = EmitRequest(message="ping", fire_at=ts)
        assert r.fire_at == ts

    def test_missing_message(self) -> None:
        with pytest.raises(ValidationError):
            EmitRequest()  # type: ignore[call-arg]

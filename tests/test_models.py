import pytest
from pydantic import ValidationError

from trigr.models import (
    ActionConfig,
    CronSchedule,
    TaskConfig,
    TriggerConfig,
    TriggerType,
)


def test_cron_trigger_valid():
    t = TriggerConfig(type=TriggerType.cron, cron=CronSchedule(hour=7, minute=0))
    assert t.type == TriggerType.cron
    assert t.cron.hour == 7


def test_cron_trigger_missing_cron():
    with pytest.raises(ValidationError, match="cron trigger requires"):
        TriggerConfig(type=TriggerType.cron)


def test_interval_trigger_valid():
    t = TriggerConfig(type=TriggerType.interval, interval_seconds=60)
    assert t.interval_seconds == 60


def test_interval_trigger_missing_seconds():
    with pytest.raises(ValidationError, match="interval trigger requires"):
        TriggerConfig(type=TriggerType.interval)


def test_watch_trigger_valid():
    t = TriggerConfig(type=TriggerType.watch, watch_paths=["/tmp/test"])
    assert t.watch_paths == ["/tmp/test"]


def test_watch_trigger_missing_paths():
    with pytest.raises(ValidationError, match="watch trigger requires"):
        TriggerConfig(type=TriggerType.watch)


def test_script_action_valid():
    a = ActionConfig(type="script", command="echo hello")
    assert a.command == "echo hello"


def test_script_action_missing_command():
    with pytest.raises(ValidationError, match="script action requires"):
        ActionConfig(type="script")


def test_claude_action_valid():
    a = ActionConfig(type="claude", prompt="do stuff")
    assert a.prompt == "do stuff"


def test_claude_action_missing_prompt():
    with pytest.raises(ValidationError, match="claude action requires"):
        ActionConfig(type="claude")


def test_unknown_action_type():
    with pytest.raises(ValidationError, match="unknown action type"):
        ActionConfig(type="webhook", command="test")


def test_full_task_config():
    task = TaskConfig(
        name="test-task",
        description="A test",
        trigger=TriggerConfig(type=TriggerType.interval, interval_seconds=60),
        action=ActionConfig(type="script", command="echo hi"),
    )
    assert task.name == "test-task"
    assert task.enabled is True
    assert task.notify.on_failure is True
    assert task.notify.on_success is False

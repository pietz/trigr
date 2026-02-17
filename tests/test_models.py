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
    a = ActionConfig(command="echo hello")
    assert a.command == "echo hello"


def test_script_action_missing_both():
    with pytest.raises(ValidationError, match="action requires either command or prompt"):
        ActionConfig()


def test_prompt_action_valid():
    a = ActionConfig(prompt="do stuff")
    assert a.prompt == "do stuff"


def test_prompt_action_with_provider():
    a = ActionConfig(prompt="do stuff", provider="gemini")
    assert a.provider == "gemini"


def test_prompt_action_with_model():
    a = ActionConfig(prompt="do stuff", provider="codex", model="gpt-5.2")
    assert a.model == "gpt-5.2"


def test_both_command_and_prompt():
    with pytest.raises(ValidationError, match="cannot have both command and prompt"):
        ActionConfig(command="echo hi", prompt="do stuff")


def test_provider_without_prompt():
    with pytest.raises(ValidationError, match="provider requires prompt"):
        ActionConfig(command="echo hi", provider="claude")


def test_model_without_prompt():
    with pytest.raises(ValidationError, match="model requires prompt"):
        ActionConfig(command="echo hi", model="gpt-5")


def test_unknown_provider():
    with pytest.raises(ValidationError, match="unknown provider"):
        ActionConfig(prompt="do stuff", provider="openai")


def test_full_task_config():
    task = TaskConfig(
        name="test-task",
        description="A test",
        trigger=TriggerConfig(type=TriggerType.interval, interval_seconds=60),
        action=ActionConfig(command="echo hi"),
    )
    assert task.name == "test-task"
    assert task.enabled is True
    assert task.notify.on_failure is True
    assert task.notify.on_success is False


def test_action_env_default():
    a = ActionConfig(command="echo hi")
    assert a.env == {}


def test_action_env_set():
    a = ActionConfig(command="echo hi", env={"API_KEY": "sk-123", "VERBOSE": "1"})
    assert a.env["API_KEY"] == "sk-123"
    assert a.env["VERBOSE"] == "1"


def test_notify_max_consecutive_failures_default():
    from trigr.models import NotifyConfig
    n = NotifyConfig()
    assert n.max_consecutive_failures == 0


def test_notify_max_consecutive_failures_set():
    from trigr.models import NotifyConfig
    n = NotifyConfig(max_consecutive_failures=5)
    assert n.max_consecutive_failures == 5

from unittest.mock import patch

from trigr.models import (
    ActionConfig,
    CronSchedule,
    TaskConfig,
    TriggerConfig,
    TriggerType,
)
from trigr.plist import generate_plist, plist_label


def _make_task(trigger: TriggerConfig) -> TaskConfig:
    return TaskConfig(
        name="test-task",
        trigger=trigger,
        action=ActionConfig(type="script", command="echo hi"),
    )


def test_plist_label():
    assert plist_label("my-task") == "com.trigr.my-task"


@patch("trigr.plist.get_trigr_path", return_value="/usr/local/bin/trigr")
@patch("trigr.plist.load_env", return_value={"PATH": "/usr/bin", "HOME": "/Users/test"})
def test_generate_plist_interval(mock_env, mock_path):
    task = _make_task(TriggerConfig(type=TriggerType.interval, interval_seconds=120))
    plist = generate_plist(task)

    assert plist["Label"] == "com.trigr.test-task"
    assert plist["ProgramArguments"] == ["/usr/local/bin/trigr", "run", "test-task"]
    assert plist["StartInterval"] == 120
    assert "StartCalendarInterval" not in plist
    assert "WatchPaths" not in plist


@patch("trigr.plist.get_trigr_path", return_value="/usr/local/bin/trigr")
@patch("trigr.plist.load_env", return_value={"PATH": "/usr/bin"})
def test_generate_plist_cron(mock_env, mock_path):
    task = _make_task(
        TriggerConfig(type=TriggerType.cron, cron=CronSchedule(hour=7, minute=30))
    )
    plist = generate_plist(task)

    assert plist["StartCalendarInterval"] == {"Hour": 7, "Minute": 30}
    assert "StartInterval" not in plist


@patch("trigr.plist.get_trigr_path", return_value="/usr/local/bin/trigr")
@patch("trigr.plist.load_env", return_value={"PATH": "/usr/bin"})
def test_generate_plist_watch(mock_env, mock_path):
    task = _make_task(
        TriggerConfig(type=TriggerType.watch, watch_paths=["/tmp/watched"])
    )
    plist = generate_plist(task)

    assert "/tmp/watched" in plist["WatchPaths"][0]
    assert "StartInterval" not in plist

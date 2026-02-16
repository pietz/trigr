from enum import Enum

from pydantic import BaseModel, model_validator


class TriggerType(str, Enum):
    cron = "cron"
    interval = "interval"
    watch = "watch"


class CronSchedule(BaseModel):
    minute: int | None = None
    hour: int | None = None
    day: int | None = None  # day of month
    weekday: int | None = None  # 0=Sunday
    month: int | None = None


class TriggerConfig(BaseModel):
    type: TriggerType
    cron: CronSchedule | None = None
    interval_seconds: int | None = None
    watch_paths: list[str] | None = None

    @model_validator(mode="after")
    def validate_trigger(self) -> "TriggerConfig":
        match self.type:
            case TriggerType.cron:
                if self.cron is None:
                    raise ValueError("cron trigger requires [trigger.cron] section")
            case TriggerType.interval:
                if self.interval_seconds is None:
                    raise ValueError("interval trigger requires interval_seconds")
            case TriggerType.watch:
                if not self.watch_paths:
                    raise ValueError("watch trigger requires watch_paths")
        return self


class ActionConfig(BaseModel):
    type: str  # "script" or "claude"
    command: str | None = None
    prompt: str | None = None
    working_dir: str | None = None
    timeout: int = 300

    @model_validator(mode="after")
    def validate_action(self) -> "ActionConfig":
        if self.type == "script" and not self.command:
            raise ValueError("script action requires command")
        if self.type == "claude" and not self.prompt:
            raise ValueError("claude action requires prompt")
        if self.type not in ("script", "claude"):
            raise ValueError(f"unknown action type: {self.type}")
        return self


class NotifyConfig(BaseModel):
    on_success: bool = False
    on_failure: bool = True
    title: str | None = None


class TaskConfig(BaseModel):
    name: str
    description: str = ""
    trigger: TriggerConfig
    action: ActionConfig
    notify: NotifyConfig = NotifyConfig()
    enabled: bool = True

from enum import Enum

from pydantic import BaseModel, field_validator, model_validator


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

    @field_validator("minute")
    @classmethod
    def check_minute(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 59):
            raise ValueError(f"minute must be 0-59, got {v}")
        return v

    @field_validator("hour")
    @classmethod
    def check_hour(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 23):
            raise ValueError(f"hour must be 0-23, got {v}")
        return v

    @field_validator("day")
    @classmethod
    def check_day(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 31):
            raise ValueError(f"day must be 1-31, got {v}")
        return v

    @field_validator("weekday")
    @classmethod
    def check_weekday(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 6):
            raise ValueError(f"weekday must be 0-6, got {v}")
        return v

    @field_validator("month")
    @classmethod
    def check_month(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 12):
            raise ValueError(f"month must be 1-12, got {v}")
        return v


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


PROVIDERS = {
    "claude": {"binary": "claude", "prompt_flag": "-p", "model_flag": "--model"},
    "codex": {"binary": "codex", "prompt_flag": "exec", "model_flag": "-m"},
    "gemini": {"binary": "gemini", "prompt_flag": "-p", "model_flag": "-m"},
}


class ActionConfig(BaseModel):
    command: str | None = None
    prompt: str | None = None
    provider: str | None = None
    model: str | None = None
    working_dir: str | None = None
    timeout: int = 300
    env: dict[str, str] = {}

    @model_validator(mode="after")
    def validate_action(self) -> "ActionConfig":
        if self.command and self.prompt:
            raise ValueError("action cannot have both command and prompt")
        if not self.command and not self.prompt:
            raise ValueError("action requires either command or prompt")
        if self.provider and not self.prompt:
            raise ValueError("provider requires prompt")
        if self.model and not self.prompt:
            raise ValueError("model requires prompt")
        if self.provider and self.provider not in PROVIDERS:
            raise ValueError(f"unknown provider: {self.provider} (must be one of {', '.join(PROVIDERS)})")
        return self


class NotifyConfig(BaseModel):
    on_success: bool = False
    on_failure: bool = True
    title: str | None = None
    max_consecutive_failures: int = 0  # 0 = never auto-disable


class TaskConfig(BaseModel):
    name: str
    description: str = ""
    trigger: TriggerConfig
    action: ActionConfig
    notify: NotifyConfig = NotifyConfig()
    enabled: bool = True

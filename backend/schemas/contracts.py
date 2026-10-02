from datetime import date, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TelegramIdentity(BaseModel):
    telegram_identifier: int = Field(gt=0)


class HabitInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    start_date: date
    end_date: date | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, title):
        title = title.strip()
        if not title:
            raise ValueError("Название не может быть пустым")
        return title

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("Дата окончания раньше даты начала")
        return self


class HabitOutput(HabitInput):
    model_config = ConfigDict(from_attributes=True)
    identifier: int
    completion_count: int
    completed: bool | None = None
    record_date: date | None = None
    archived: bool = False


class CompletionInput(BaseModel):
    completed: bool
    record_date: date


class ReminderInput(BaseModel):
    timezone_name: str
    reminder_time: time
    reminders_enabled: bool = True

    @field_validator("timezone_name")
    @classmethod
    def validate_timezone(cls, timezone_name):
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Неизвестный часовой пояс IANA") from error
        return timezone_name

    @field_validator("reminder_time")
    @classmethod
    def validate_reminder_time(cls, reminder_time):
        if reminder_time.tzinfo or reminder_time.second or reminder_time.microsecond:
            raise ValueError("Используйте локальное время HH:MM")
        return reminder_time

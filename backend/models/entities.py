from datetime import date, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    identifier: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_identifier: Mapped[int] = mapped_column(BigInteger, unique=True)
    timezone_name: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    reminder_time: Mapped[time] = mapped_column(Time, default=time(20))
    last_reminder_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_reminder_attempt: Mapped[int] = mapped_column(BigInteger, default=0)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Habit(Base):
    __tablename__ = "habits"
    __table_args__ = (CheckConstraint("completion_count >= 0"),)
    identifier: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_identifier: Mapped[int] = mapped_column(
        ForeignKey("users.identifier", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(1000), default="")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completion_count: Mapped[int] = mapped_column(Integer, default=0)


class DailyRecord(Base):
    __tablename__ = "daily_records"
    __table_args__ = (UniqueConstraint("habit_identifier", "record_date"),)
    identifier: Mapped[int] = mapped_column(Integer, primary_key=True)
    habit_identifier: Mapped[int] = mapped_column(
        ForeignKey("habits.identifier", ondelete="CASCADE"), index=True
    )
    record_date: Mapped[date] = mapped_column(Date)
    completed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

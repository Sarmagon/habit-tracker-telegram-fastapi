from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select

from backend.models.entities import DailyRecord, Habit, User
from backend.schemas.contracts import HabitOutput


def get_local_date(user, current_time=None):
    return (
        (current_time or datetime.now(UTC))
        .astimezone(ZoneInfo(user.timezone_name))
        .date()
    )


def lock_user(database_session, user_identifier):
    return database_session.scalar(
        select(User).where(User.identifier == user_identifier).with_for_update()
    )


def get_owned_habit(database_session, user_identifier, habit_identifier):
    habit = database_session.scalar(
        select(Habit).where(
            Habit.identifier == habit_identifier,
            Habit.owner_identifier == user_identifier,
        )
    )
    if habit is None:
        raise HTTPException(404, "Привычка не найдена")
    return habit


def is_habit_active(habit, record_date, completion_limit):
    return (
        habit.start_date <= record_date
        and (habit.end_date is None or record_date <= habit.end_date)
        and habit.completion_count < completion_limit
    )


def ensure_daily_records(database_session, user, completion_limit, current_time=None):
    record_date = get_local_date(user, current_time)
    habits = database_session.scalars(
        select(Habit).where(Habit.owner_identifier == user.identifier)
    ).all()
    for habit in habits:
        if not is_habit_active(habit, record_date, completion_limit):
            continue
        record = database_session.scalar(
            select(DailyRecord).where(
                DailyRecord.habit_identifier == habit.identifier,
                DailyRecord.record_date == record_date,
            )
        )
        if record is None:
            database_session.add(
                DailyRecord(habit_identifier=habit.identifier, record_date=record_date)
            )
    database_session.flush()
    return record_date


def list_habits(
    database_session, user, completion_limit, include_archive=False, current_time=None
):
    record_date = ensure_daily_records(
        database_session, user, completion_limit, current_time
    )
    habits = database_session.scalars(
        select(Habit)
        .where(Habit.owner_identifier == user.identifier)
        .order_by(Habit.identifier)
    ).all()
    results = []
    for habit in habits:
        record = database_session.scalar(
            select(DailyRecord).where(
                DailyRecord.habit_identifier == habit.identifier,
                DailyRecord.record_date == record_date,
            )
        )
        archived = habit.completion_count >= completion_limit
        # The final successful day's record stays visible until midnight.
        if not include_archive and not (
            is_habit_active(habit, record_date, completion_limit)
            or (record is not None and record.completed is True)
        ):
            continue
        result = HabitOutput.model_validate(habit)
        result.completed = record.completed if record else None
        result.record_date = record_date if record else None
        result.archived = archived
        results.append(result)
    return results


def mark_completion(
    database_session, user, habit_identifier, completed, record_date, completion_limit
):
    habit = get_owned_habit(database_session, user.identifier, habit_identifier)
    if record_date != get_local_date(user):
        raise HTTPException(409, "Отмечать можно только текущий день")
    ensure_daily_records(database_session, user, completion_limit)
    record = database_session.scalar(
        select(DailyRecord).where(
            DailyRecord.habit_identifier == habit.identifier,
            DailyRecord.record_date == record_date,
        )
    )
    if (
        record is None
        or habit.start_date > record_date
        or (habit.end_date is not None and record_date > habit.end_date)
    ):
        raise HTTPException(409, "Привычка недоступна в этот день")
    previous_completed = record.completed is True
    habit.completion_count += int(completed) - int(previous_completed)
    record.completed = completed
    database_session.flush()
    return habit

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from backend.models.entities import DailyRecord, Habit
from backend.services.habits import (
    ensure_daily_records,
    get_local_date,
    get_owned_habit,
    list_habits,
    mark_completion,
)


def create_test_habit(database_session, user, **values):
    habit = Habit(
        owner_identifier=user.identifier,
        title="Пить воду",
        start_date=get_local_date(user),
        **values,
    )
    database_session.add(habit)
    database_session.commit()
    return habit


def test_repeated_mark_is_idempotent_and_can_be_reversed(database_session, user):
    habit = create_test_habit(database_session, user)
    today = get_local_date(user)
    for completed in [True, True, True]:
        mark_completion(database_session, user, habit.identifier, completed, today, 21)
    assert habit.completion_count == 1
    mark_completion(database_session, user, habit.identifier, False, today, 21)
    mark_completion(database_session, user, habit.identifier, False, today, 21)
    assert habit.completion_count == 0
    assert database_session.scalar(select(func.count()).select_from(DailyRecord)) == 1


def test_limit_removes_habit_from_next_day_but_preserves_history(
    database_session, user
):
    habit = create_test_habit(database_session, user, completion_count=20)
    mark_completion(
        database_session, user, habit.identifier, True, get_local_date(user), 21
    )
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    ensure_daily_records(database_session, user, 21, tomorrow)
    records = database_session.scalars(select(DailyRecord)).all()
    assert habit.completion_count == 21
    assert len(records) == 1
    assert records[0].completed is True
    assert list_habits(database_session, user, 21, current_time=tomorrow) == []
    assert len(list_habits(database_session, user, 21, True, tomorrow)) == 1


def test_completion_limit_is_configurable(database_session, user):
    habit = create_test_habit(database_session, user)
    mark_completion(
        database_session, user, habit.identifier, True, get_local_date(user), 1
    )
    assert habit.completion_count == 1
    assert (
        list_habits(
            database_session,
            user,
            1,
            current_time=datetime.now(UTC) + timedelta(days=1),
        )
        == []
    )


@pytest.mark.parametrize("completed", [None, False, True])
def test_rollover_resets_status_without_losing_history(
    database_session, user, completed
):
    habit = create_test_habit(database_session, user)
    if completed is None:
        ensure_daily_records(database_session, user, 21)
    else:
        mark_completion(
            database_session,
            user,
            habit.identifier,
            completed,
            get_local_date(user),
            21,
        )
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    for _ in range(3):
        ensure_daily_records(database_session, user, 21, tomorrow)
    records = database_session.scalars(
        select(DailyRecord).order_by(DailyRecord.record_date)
    ).all()
    assert len(records) == 2
    assert records[0].completed is completed
    assert records[1].completed is None


def test_start_and_end_dates_control_rollover(database_session, user):
    habit = create_test_habit(database_session, user, end_date=get_local_date(user))
    ensure_daily_records(
        database_session, user, 21, datetime.now(UTC) + timedelta(days=1)
    )
    assert database_session.scalar(select(func.count()).select_from(DailyRecord)) == 0
    habit.start_date = get_local_date(user) + timedelta(days=2)
    habit.end_date = None
    ensure_daily_records(database_session, user, 21)
    assert database_session.scalar(select(func.count()).select_from(DailyRecord)) == 0


def test_old_callback_cannot_mark_another_day(database_session, user):
    habit = create_test_habit(database_session, user)
    with pytest.raises(HTTPException) as error:
        mark_completion(
            database_session,
            user,
            habit.identifier,
            True,
            get_local_date(user) - timedelta(days=1),
            21,
        )
    assert error.value.status_code == 409
    assert habit.completion_count == 0


def test_another_user_cannot_access_habit(database_session, user):
    habit = create_test_habit(database_session, user)
    with pytest.raises(HTTPException) as error:
        get_owned_habit(database_session, user.identifier + 1, habit.identifier)
    assert error.value.status_code == 404


def test_midnight_uses_users_timezone(user):
    user.timezone_name = "Asia/Tokyo"
    assert (
        str(get_local_date(user, datetime(2026, 1, 1, 16, tzinfo=UTC))) == "2026-01-02"
    )
    user.timezone_name = "America/New_York"
    assert (
        str(get_local_date(user, datetime(2026, 1, 1, 3, tzinfo=UTC))) == "2025-12-31"
    )


def test_edited_future_habit_cannot_be_marked_today(database_session, user):
    habit = create_test_habit(database_session, user)
    ensure_daily_records(database_session, user, 21)
    habit.start_date = get_local_date(user) + timedelta(days=1)
    with pytest.raises(HTTPException) as error:
        mark_completion(
            database_session, user, habit.identifier, True, get_local_date(user), 21
        )
    assert error.value.status_code == 409

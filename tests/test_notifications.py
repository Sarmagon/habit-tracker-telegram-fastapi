from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from sqlalchemy.orm import sessionmaker

from backend.services import notifications
from common.config import Settings
from tests.test_habits import create_test_habit


def test_reminder_is_sent_once_and_retried_after_failure(
    database_session, user, monkeypatch
):
    user.timezone_name = "UTC"
    database_session.commit()
    create_test_habit(database_session, user)
    monkeypatch.setattr(
        notifications,
        "SessionFactory",
        sessionmaker(database_session.bind, expire_on_commit=False),
    )
    current_time = datetime.now(UTC).replace(hour=21, minute=0)
    sender = Mock(side_effect=[RuntimeError("offline"), None])
    notifications.run_notification_tick(Settings(), current_time, sender)
    notifications.run_notification_tick(Settings(), current_time, sender)
    assert sender.call_count == 1
    notifications.run_notification_tick(
        Settings(), current_time + timedelta(seconds=61), sender
    )
    notifications.run_notification_tick(
        Settings(), current_time + timedelta(seconds=62), sender
    )
    assert sender.call_count == 2


def test_no_reminder_before_time_or_when_disabled(database_session, user, monkeypatch):
    user.timezone_name = "UTC"
    database_session.commit()
    create_test_habit(database_session, user)
    user.reminders_enabled = False
    database_session.commit()
    monkeypatch.setattr(
        notifications,
        "SessionFactory",
        sessionmaker(database_session.bind, expire_on_commit=False),
    )
    sender = Mock()
    notifications.run_notification_tick(
        Settings(), datetime.now(UTC).replace(hour=21), sender
    )
    assert sender.call_count == 0
    user.reminders_enabled = True
    database_session.commit()
    notifications.run_notification_tick(
        Settings(), datetime.now(UTC).replace(hour=0), sender
    )
    assert sender.call_count == 0


def test_long_reminder_is_split_into_telegram_sized_messages(monkeypatch):
    from types import SimpleNamespace

    response = Mock()
    response.json.return_value = {"ok": True}
    sender = Mock(return_value=response)
    monkeypatch.setattr(notifications.httpx, "post", sender)
    habits = [SimpleNamespace(title="a" * 120, completed=None) for _ in range(100)]
    notifications.deliver_reminder(
        SimpleNamespace(telegram_identifier=123), habits, "test-token"
    )
    assert sender.call_count > 1
    assert all(
        len(call.kwargs["json"]["text"]) < 4096 for call in sender.call_args_list
    )
    assert all(
        call.kwargs["json"]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        == "menu:today"
        for call in sender.call_args_list
    )

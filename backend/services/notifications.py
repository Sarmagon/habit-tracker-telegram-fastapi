import logging
import threading
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

from backend.database import SessionFactory
from backend.models.entities import User
from backend.services.habits import list_habits

logger = logging.getLogger(__name__)


def deliver_reminder(user, habits, telegram_token):

    pending_habits = [habit for habit in habits if habit.completed is None]

    if not pending_habits:
        return

    message_chunks = []

    current_chunk = "Пора отметить привычки:\n"

    for habit in pending_habits:
        habit_line = f"• {habit.title}\n"

        if len(current_chunk) + len(habit_line) > 3500:
            message_chunks.append(current_chunk)

            current_chunk = "Привычки (продолжение):\n"

        current_chunk += habit_line

    message_chunks.append(
        current_chunk + "Нажмите «Открыть привычки», чтобы отметить их."
    )

    for message_text in message_chunks:
        response = httpx.post(
            f"https://api.telegram.org/bot{telegram_token}/sendMessage",
            json={
                "chat_id": user.telegram_identifier,
                "text": message_text,
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {
                                "text": "Открыть привычки",
                                "callback_data": "menu:today",
                            }
                        ]
                    ]
                },
            },
            timeout=10,
        )

        response.raise_for_status()

        if not response.json().get("ok"):
            raise RuntimeError("Telegram rejected reminder")


def run_notification_tick(settings, current_time=None, sender=deliver_reminder):

    current_time = current_time or datetime.now(UTC)

    with SessionFactory() as database_session:
        user_identifiers = database_session.scalars(select(User.identifier)).all()

    for user_identifier in user_identifiers:
        with SessionFactory() as database_session:
            user = database_session.scalar(
                select(User)
                .where(User.identifier == user_identifier)
                .with_for_update(skip_locked=True)
            )

            if user is None:
                continue

            local_time = current_time.astimezone(ZoneInfo(user.timezone_name))

            # Rollover runs before the reminder check, including after downtime.

            habits = list_habits(
                database_session,
                user,
                settings.habit_completion_limit,
                current_time=current_time,
            )

            if (
                user.reminders_enabled
                and any(habit.completed is None for habit in habits)
                and local_time.time() >= user.reminder_time
                and user.last_reminder_date != local_time.date()
                and user.next_reminder_attempt <= int(current_time.timestamp())
            ):
                try:
                    sender(user, habits, settings.telegram_bot_token)

                except Exception:
                    # Do not log exception URLs: they can contain Telegram tokens.

                    logger.warning(
                        "Reminder delivery failed for user %s", user.identifier
                    )

                    user.next_reminder_attempt = int(current_time.timestamp()) + 60

                else:
                    user.last_reminder_date = local_time.date()

                    user.next_reminder_attempt = 0

            database_session.commit()


def run_notification_worker(settings, stop_event: threading.Event, worker_state):

    while not stop_event.is_set():
        try:
            run_notification_tick(settings)

            worker_state["last_success"] = time.monotonic()

        except Exception:
            logger.warning("Notification tick failed; will retry")

        stop_event.wait(settings.notification_poll_seconds)

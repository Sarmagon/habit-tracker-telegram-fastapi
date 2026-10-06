import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from telebot import types

from bot.views.messages import (
    create_dialog_keyboard,
    create_habit_keyboard,
    create_main_keyboard,
    format_habit_message,
)

MENU_COMMANDS = {
    "Сегодня": "/today",
    "Добавить привычку": "/add",
    "Все привычки": "/all",
    "Напоминания": "/reminder",
    "Помощь": "/help",
    "Отменить": "/cancel",
}

HELP_MESSAGE = (
    "Я помогу следить за привычками. Выберите действие кнопками внизу.\n"
    "/today — привычки на сегодня\n/add — добавить привычку\n"
    "/all — все привычки, включая будущие и освоенные\n"
    "/reminder — время, часовой пояс и включение напоминаний\n"
    "/cancel — отменить ввод\n\n"
    "Меняйте и удаляйте привычки кнопками под карточкой. "
    "Отметки можно исправлять в течение текущего дня."
)


class HabitPresenter:
    def __init__(self, telegram_bot, backend_client):
        self.telegram_bot = telegram_bot
        self.backend_client = backend_client
        self.conversations = {}

    def send_message(self, telegram_identifier, message, keyboard=None):
        if keyboard is None:
            conversation = self.conversations.get(telegram_identifier)
            if conversation:
                habit_buttons = {
                    0: ("Отменить",),
                    1: ("Пропустить", "Отменить"),
                    2: ("Сегодня", "Отменить"),
                    3: ("Без ограничения", "Отменить"),
                }
                reminder_buttons = {
                    0: ("Отменить",),
                    1: ("Europe/Moscow", "Asia/Yekaterinburg", "Отменить"),
                    2: ("Да", "Нет", "Отменить"),
                }
                button_labels = (
                    habit_buttons
                    if conversation["kind"] == "habit"
                    else reminder_buttons
                )[conversation["step"]]
                keyboard = create_dialog_keyboard(*button_labels)
            else:
                keyboard = create_main_keyboard()
        self.telegram_bot.send_message(
            telegram_identifier, message, reply_markup=keyboard
        )

    def display_error(self, telegram_identifier, error):
        if isinstance(error, httpx.HTTPStatusError):
            try:
                detail = error.response.json().get("detail", "Ошибка запроса")
                if isinstance(detail, list):
                    detail = "Проверьте введённые значения и даты."
                self.send_message(telegram_identifier, str(detail)[:1000])
                return
            except ValueError:
                pass
        self.send_message(
            telegram_identifier, "Сервис временно недоступен. Попробуйте ещё раз."
        )

    def display_habits(self, telegram_identifier, include_archive=False):
        habits = self.backend_client.send_request(
            telegram_identifier,
            "GET",
            "/habits?include_archive=" + str(include_archive).lower(),
        )
        if not habits:
            self.send_message(
                telegram_identifier, "Список пуст. Нажмите «Добавить привычку»."
            )
        for habit in habits:
            self.send_message(
                telegram_identifier,
                format_habit_message(habit),
                create_habit_keyboard(habit),
            )

    def start_habit_dialog(self, telegram_identifier, habit_identifier=None):
        self.conversations[telegram_identifier] = {
            "kind": "habit",
            "step": 0,
            "payload": {},
            "habit_identifier": habit_identifier,
            "expires": time.monotonic() + 900,
        }
        self.send_message(
            telegram_identifier,
            "Введите новое название привычки (до 120 символов)."
            if habit_identifier
            else "Введите название привычки (до 120 символов).",
        )

    def start_reminder_dialog(self, telegram_identifier):
        self.conversations[telegram_identifier] = {
            "kind": "reminder",
            "step": 0,
            "payload": {},
            "expires": time.monotonic() + 900,
        }
        self.send_message(
            telegram_identifier, "Введите время напоминания: HH:MM (например 20:00)."
        )

    def receive_message(self, message):
        if message.chat.type != "private" or message.from_user.is_bot:
            return
        telegram_identifier = message.from_user.id
        message_text = (message.text or "").strip()
        conversation = self.conversations.get(telegram_identifier)
        selecting_today = (
            conversation
            and conversation["kind"] == "habit"
            and conversation["step"] == 2
            and conversation["expires"] >= time.monotonic()
            and message_text == "Сегодня"
        )
        if not selecting_today:
            message_text = MENU_COMMANDS.get(message_text, message_text)
        try:
            if message_text.startswith("/"):
                command = message_text.split()[0].split("@")[0]
                self.conversations.pop(telegram_identifier, None)
                if command in {"/start", "/help"}:
                    self.send_message(telegram_identifier, HELP_MESSAGE)
                elif command in {"/today", "/all"}:
                    self.display_habits(telegram_identifier, command == "/all")
                elif command == "/add":
                    self.start_habit_dialog(telegram_identifier)
                elif command == "/reminder":
                    self.start_reminder_dialog(telegram_identifier)
                elif command == "/cancel":
                    self.send_message(telegram_identifier, "Ввод отменён.")
                else:
                    self.send_message(telegram_identifier, HELP_MESSAGE)
                return
            conversation = self.conversations.get(telegram_identifier)
            if not conversation or conversation["expires"] < time.monotonic():
                self.conversations.pop(telegram_identifier, None)
                self.send_message(
                    telegram_identifier,
                    "Выберите действие в меню. "
                    "Для создания нажмите «Добавить привычку»."
                    if not conversation
                    else "Время ввода истекло. Начните заново через меню.",
                )
                return
            if conversation["kind"] == "habit":
                self.advance_habit_dialog(
                    telegram_identifier, message_text, conversation
                )
            else:
                self.advance_reminder_dialog(
                    telegram_identifier, message_text, conversation
                )
        except (httpx.HTTPError, ValueError) as error:
            if isinstance(error, ValueError):
                self.send_message(telegram_identifier, str(error))
            else:
                self.display_error(telegram_identifier, error)

    def advance_habit_dialog(self, telegram_identifier, message_text, conversation):
        step = conversation["step"]
        payload = conversation["payload"]
        if step == 0:
            if not 1 <= len(message_text) <= 120:
                raise ValueError("Название должно содержать от 1 до 120 символов.")
            payload["title"] = message_text
            prompt = "Описание до 1000 символов, или - для пустого описания."
        elif step == 1:
            if len(message_text) > 1000:
                raise ValueError("Описание слишком длинное.")
            payload["description"] = (
                "" if message_text.lower() in {"-", "пропустить"} else message_text
            )
            prompt = "Введите дату начала в формате ГГГГ-ММ-ДД или нажмите «Сегодня»."
        elif step == 2:
            if message_text.lower() == "сегодня":
                profile = self.backend_client.send_request(
                    telegram_identifier, "GET", "/profile"
                )
                message_text = (
                    datetime.now(ZoneInfo(profile["timezone_name"])).date().isoformat()
                )
            payload["start_date"] = self.parse_habit_date(message_text)
            prompt = (
                "Введите дату окончания в формате ГГГГ-ММ-ДД "
                "или нажмите «Без ограничения». Можно отправить только знак -."
            )
        else:
            payload["end_date"] = (
                None
                if message_text.lower() in {"-", "без ограничения", "- без ограничения"}
                else self.parse_habit_date(message_text)
            )
            if payload["end_date"] and payload["end_date"] < payload["start_date"]:
                raise ValueError("Дата окончания раньше начала. Введите её заново.")
            habit_identifier = conversation["habit_identifier"]
            path = f"/habits/{habit_identifier}" if habit_identifier else "/habits"
            self.backend_client.send_request(
                telegram_identifier,
                "PUT" if habit_identifier else "POST",
                path,
                payload,
            )
            self.conversations.pop(telegram_identifier, None)
            self.send_message(telegram_identifier, "Привычка сохранена.")
            self.display_habits(telegram_identifier, include_archive=True)
            return
        conversation["step"] += 1
        keyboard_labels = {
            1: ("Пропустить", "Отменить"),
            2: ("Сегодня", "Отменить"),
            3: ("Без ограничения", "Отменить"),
        }
        self.send_message(
            telegram_identifier,
            prompt,
            create_dialog_keyboard(*keyboard_labels[conversation["step"]]),
        )

    def parse_habit_date(self, message_text):
        try:
            return datetime.strptime(message_text, "%Y-%m-%d").date().isoformat()
        except ValueError as error:
            raise ValueError(
                "Не удалось распознать дату. Введите существующую дату "
                "в формате ГГГГ-ММ-ДД, например 2026-10-06. "
                "Для окончания без ограничения нажмите «Без ограничения»."
            ) from error

    def advance_reminder_dialog(self, telegram_identifier, message_text, conversation):
        payload = conversation["payload"]
        if conversation["step"] == 0:
            try:
                payload["reminder_time"] = (
                    datetime.strptime(message_text, "%H:%M").time().isoformat()
                )
            except ValueError as error:
                raise ValueError(
                    "Введите время в формате ЧЧ:ММ от 00:00 до 23:59, например 20:00."
                ) from error
            prompt = "Часовой пояс IANA, например Europe/Moscow или Asia/Yekaterinburg."
        elif conversation["step"] == 1:
            try:
                ZoneInfo(message_text)
            except KeyError as error:
                raise ValueError(
                    "Неизвестный часовой пояс. Попробуйте ещё раз."
                ) from error
            payload["timezone_name"] = message_text
            prompt = "Включить напоминания? Введите да или нет."
        else:
            if message_text.lower() not in {"да", "нет"}:
                raise ValueError("Введите да или нет.")
            payload["reminders_enabled"] = message_text.lower() == "да"
            self.backend_client.send_request(
                telegram_identifier, "PUT", "/settings/reminder", payload
            )
            self.conversations.pop(telegram_identifier, None)
            self.send_message(telegram_identifier, "Настройки напоминаний сохранены.")
            return
        conversation["step"] += 1
        self.send_message(
            telegram_identifier,
            prompt,
            create_dialog_keyboard(
                *("Europe/Moscow", "Asia/Yekaterinburg", "Отменить")
                if conversation["step"] == 1
                else ("Да", "Нет", "Отменить")
            ),
        )

    def receive_callback(self, callback):
        if callback.message is None or callback.message.chat.type != "private":
            return
        telegram_identifier = callback.from_user.id
        if callback.message.chat.id != telegram_identifier:
            return
        self.telegram_bot.answer_callback_query(callback.id)
        try:
            if callback.data == "menu:today":
                self.conversations.pop(telegram_identifier, None)
                self.send_message(telegram_identifier, "Ваши привычки на сегодня:")
                self.display_habits(telegram_identifier)
                return
            parts = callback.data.split(":")
            action, habit_identifier = parts[:2]
            habit_identifier = int(habit_identifier)
            if action == "mark":
                self.backend_client.send_request(
                    telegram_identifier,
                    "POST",
                    f"/habits/{habit_identifier}/completion",
                    {"completed": parts[2] == "1", "record_date": parts[3]},
                )
                self.display_habits(telegram_identifier)
            elif action == "edit":
                self.start_habit_dialog(telegram_identifier, habit_identifier)
            elif action == "delete":
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(
                    types.InlineKeyboardButton(
                        "Подтвердить удаление",
                        callback_data=f"confirm:{habit_identifier}",
                    )
                )
                keyboard.add(
                    types.InlineKeyboardButton(
                        "Оставить привычку", callback_data=f"keep:{habit_identifier}"
                    )
                )
                self.send_message(
                    telegram_identifier, "Удалить привычку и её историю?", keyboard
                )
            elif action == "keep":
                self.send_message(telegram_identifier, "Удаление отменено.")
            elif action == "confirm":
                self.backend_client.send_request(
                    telegram_identifier, "DELETE", f"/habits/{habit_identifier}"
                )
                self.send_message(telegram_identifier, "Привычка удалена.")
            elif action == "history":
                records = self.backend_client.send_request(
                    telegram_identifier, "GET", f"/habits/{habit_identifier}/history"
                )
                history = "\n".join(
                    f"{record['record_date']}: "
                    + {True: "выполнено", False: "не выполнено", None: "без отметки"}[
                        record["completed"]
                    ]
                    for record in records
                )
                self.send_message(telegram_identifier, history or "История пока пуста.")
        except (httpx.HTTPError, ValueError, IndexError) as error:
            self.display_error(telegram_identifier, error)

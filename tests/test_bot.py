import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet

from bot.models.api_client import BackendClient
from bot.presenters.habit_presenter import HabitPresenter
from bot.views.messages import create_habit_keyboard
from common.config import Settings


def create_message(message_text, chat_type="private"):
    return SimpleNamespace(
        text=message_text,
        chat=SimpleNamespace(type=chat_type, id=123),
        from_user=SimpleNamespace(id=123, is_bot=False),
    )


def test_complete_creation_dialog_uses_backend():
    telegram_bot = Mock()
    backend_client = Mock()
    backend_client.send_request.return_value = []
    presenter = HabitPresenter(telegram_bot, backend_client)
    for message_text in ["/add", "Читать", "10 страниц", "2026-10-02", "-"]:
        presenter.receive_message(create_message(message_text))
    backend_client.send_request.assert_any_call(
        123,
        "POST",
        "/habits",
        {
            "title": "Читать",
            "description": "10 страниц",
            "start_date": "2026-10-02",
            "end_date": None,
        },
    )
    assert 123 not in presenter.conversations


def test_bot_rejects_group_messages_and_cancel_clears_dialog():
    telegram_bot = Mock()
    backend_client = Mock()
    presenter = HabitPresenter(telegram_bot, backend_client)
    presenter.receive_message(create_message("/add", "group"))
    telegram_bot.send_message.assert_not_called()
    presenter.receive_message(create_message("/add"))
    presenter.receive_message(create_message("/cancel"))
    assert presenter.conversations == {}
    backend_client.send_request.assert_not_called()


def test_mark_callback_carries_original_date():
    habit = {"identifier": 42, "record_date": "2026-10-02"}
    keyboard = create_habit_keyboard(habit).to_dict()
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "mark:42:1:2026-10-02"


def test_token_cache_and_unauthorized_refresh(tmp_path):
    client = BackendClient(
        Settings(
            bot_token_database_path=str(tmp_path / "tokens.sqlite3"),
            bot_token_encryption_key=Fernet.generate_key().decode(),
        )
    )
    first_token_response = Mock()
    first_token_response.json.return_value = {
        "access_token": "first",
        "expires_in": 900,
    }
    second_token_response = Mock()
    second_token_response.json.return_value = {
        "access_token": "second",
        "expires_in": 900,
    }
    client.http_client = Mock()
    client.http_client.post.side_effect = [first_token_response, second_token_response]
    unauthorized = Mock(status_code=401, content=b"{}")
    success = Mock(status_code=200, content=b"[]")
    success.json.return_value = []
    client.http_client.request.side_effect = [unauthorized, success, success]
    assert client.send_request(123, "GET", "/habits") == []
    assert client.send_request(123, "GET", "/habits") == []
    assert client.http_client.post.call_count == 2
    assert client.http_client.request.call_args.kwargs["headers"] == {
        "Authorization": "Bearer second"
    }


def test_main_menu_buttons_and_context_today_complete_creation():
    telegram_bot = Mock()
    backend_client = Mock()
    backend_client.send_request.side_effect = [
        {"timezone_name": "Europe/Moscow"},
        {},
        [],
    ]
    presenter = HabitPresenter(telegram_bot, backend_client)
    for message_text in [
        "Добавить привычку",
        "Читать",
        "Пропустить",
        "Сегодня",
        "Без ограничения",
    ]:
        presenter.receive_message(create_message(message_text))
    creation_call = backend_client.send_request.call_args_list[1]
    assert creation_call.args[:3] == (123, "POST", "/habits")
    assert creation_call.args[3]["end_date"] is None
    assert creation_call.args[3]["description"] == ""
    assert presenter.conversations == {}
    keyboard = json.loads(
        telegram_bot.send_message.call_args.kwargs["reply_markup"].to_json()
    )
    assert keyboard["is_persistent"] is True
    assert keyboard["keyboard"][0][0]["text"] == "Сегодня"


@pytest.mark.parametrize("invalid_date", ["не дата", "2026-02-30"])
def test_invalid_date_keeps_dialog_and_shows_russian_hint(invalid_date):
    telegram_bot = Mock()
    backend_client = Mock()
    presenter = HabitPresenter(telegram_bot, backend_client)
    for message_text in ["/add", "Читать", "-", invalid_date]:
        presenter.receive_message(create_message(message_text))
    assert presenter.conversations[123]["step"] == 2
    assert "Не удалось распознать дату" in telegram_bot.send_message.call_args.args[1]
    backend_client.send_request.assert_not_called()


def test_today_menu_outside_dialog_reads_habits():
    backend_client = Mock()
    backend_client.send_request.return_value = []
    presenter = HabitPresenter(Mock(), backend_client)
    presenter.receive_message(create_message("Сегодня"))
    backend_client.send_request.assert_called_once_with(
        123, "GET", "/habits?include_archive=false"
    )


def test_cancel_button_discards_incomplete_habit():
    backend_client = Mock()
    presenter = HabitPresenter(Mock(), backend_client)
    for message_text in ["Добавить привычку", "Читать", "Отменить"]:
        presenter.receive_message(create_message(message_text))
    assert presenter.conversations == {}
    backend_client.send_request.assert_not_called()


def test_invalid_reminder_time_keeps_dialog_without_technical_error():
    telegram_bot = Mock()
    backend_client = Mock()
    presenter = HabitPresenter(telegram_bot, backend_client)
    for message_text in ["Напоминания", "25:70"]:
        presenter.receive_message(create_message(message_text))
    assert presenter.conversations[123]["step"] == 0
    assert "Введите время" in telegram_bot.send_message.call_args.args[1]
    backend_client.send_request.assert_not_called()


def test_reminder_button_opens_current_habits():
    backend_client = Mock()
    backend_client.send_request.return_value = []
    presenter = HabitPresenter(Mock(), backend_client)
    presenter.receive_callback(
        SimpleNamespace(
            id="callback",
            data="menu:today",
            from_user=SimpleNamespace(id=123),
            message=SimpleNamespace(chat=SimpleNamespace(id=123, type="private")),
        )
    )
    backend_client.send_request.assert_called_once_with(
        123, "GET", "/habits?include_archive=false"
    )

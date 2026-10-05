import json
import logging
import threading
import time
from pathlib import Path

import telebot

from bot.models.api_client import BackendClient
from bot.presenters.habit_presenter import HabitPresenter
from common.config import Settings


def run_telegram_bot():
    settings = Settings()
    runtime_secrets = json.loads(Path(settings.secret_file).read_text(encoding="utf-8"))
    settings.bot_service_secret = runtime_secrets["bot_service_secret"]
    settings.bot_token_encryption_key = runtime_secrets["bot_token_encryption_key"]
    # Never print the token or HTTP exceptions containing Telegram URLs.
    if not settings.telegram_bot_token or settings.telegram_bot_token.startswith(
        "replace"
    ):
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env using BotFather")
    telebot.logger.setLevel(logging.CRITICAL)
    telegram_bot = telebot.TeleBot(settings.telegram_bot_token, threaded=False)
    backend_client = BackendClient(settings)
    presenter = HabitPresenter(telegram_bot, backend_client)
    telegram_bot.register_message_handler(
        presenter.receive_message, content_types=["text"]
    )
    telegram_bot.register_callback_query_handler(
        presenter.receive_callback, func=lambda callback: True
    )

    def update_heartbeat():
        while True:
            try:
                telegram_bot.get_me()
                Path("/tmp/bot-heartbeat").touch()
            except Exception:
                pass
            time.sleep(30)

    threading.Thread(target=update_heartbeat, daemon=True).start()
    try:
        telegram_bot.infinity_polling(
            skip_pending=False,
            timeout=20,
            long_polling_timeout=20,
            allowed_updates=["message", "callback_query"],
        )
    finally:
        backend_client.close_client()


if __name__ == "__main__":
    run_telegram_bot()

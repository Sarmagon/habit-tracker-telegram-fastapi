"""Trusted local operator helper; never exposes the internal bot service secret."""

import argparse
import json
from pathlib import Path

import httpx

from common.config import Settings


def issue_swagger_token():
    argument_parser = argparse.ArgumentParser(
        description="Issue a JWT for a LOCAL operator's Swagger check"
    )
    argument_parser.add_argument("--telegram-id", type=int, required=True)
    arguments = argument_parser.parse_args()
    if arguments.telegram_id <= 0:
        argument_parser.error("Telegram ID must be positive")
    settings = Settings()
    runtime_secrets = json.loads(Path(settings.secret_file).read_text(encoding="utf-8"))
    response = httpx.post(
        settings.backend_url + "/api/v1/auth/telegram",
        headers={"X-Bot-Service-Secret": runtime_secrets["bot_service_secret"]},
        json={"telegram_identifier": arguments.telegram_id},
        timeout=15,
    )
    response.raise_for_status()
    # This explicitly requested CLI output is a short-lived user credential.
    # Do not include it in recordings or publish it. The machine secret stays private.
    print(response.json()["access_token"])


if __name__ == "__main__":
    issue_swagger_token()

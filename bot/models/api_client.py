import time

import httpx


class BackendClient:
    def __init__(self, settings):
        self.settings = settings
        self.http_client = httpx.Client(
            base_url=settings.backend_url + "/api/v1", timeout=15
        )
        self.access_tokens = {}

    def obtain_access_token(self, telegram_identifier):
        response = self.http_client.post(
            "/auth/telegram",
            headers={"X-Bot-Service-Secret": self.settings.bot_service_secret},
            json={"telegram_identifier": telegram_identifier},
        )
        response.raise_for_status()
        token_data = response.json()
        self.access_tokens[telegram_identifier] = (
            token_data["access_token"],
            time.monotonic() + token_data["expires_in"] - 30,
        )
        return token_data["access_token"]

    def send_request(self, telegram_identifier, method, path, payload=None):
        cached_token = self.access_tokens.get(telegram_identifier)
        access_token = (
            cached_token[0]
            if cached_token and cached_token[1] > time.monotonic()
            else self.obtain_access_token(telegram_identifier)
        )
        response = self.http_client.request(
            method,
            path,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code == 401:
            access_token = self.obtain_access_token(telegram_identifier)
            response = self.http_client.request(
                method,
                path,
                json=payload,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        response.raise_for_status()
        return response.json() if response.content else None

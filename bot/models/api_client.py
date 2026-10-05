import httpx

from bot.models.token_store import TokenStore


class BackendClient:
    def __init__(self, settings, token_store=None):
        self.settings = settings
        self.http_client = httpx.Client(
            base_url=settings.backend_url + "/api/v1", timeout=15
        )
        self.token_store = token_store or TokenStore(
            settings.bot_token_database_path, settings.bot_token_encryption_key
        )

    def obtain_access_token(self, telegram_identifier):
        response = self.http_client.post(
            "/auth/telegram",
            headers={"X-Bot-Service-Secret": self.settings.bot_service_secret},
            json={"telegram_identifier": telegram_identifier},
        )
        response.raise_for_status()
        token_data = response.json()
        self.token_store.save_access_token(
            telegram_identifier, token_data["access_token"], token_data["expires_in"]
        )
        return token_data["access_token"]

    def send_request(self, telegram_identifier, method, path, payload=None):
        access_token = self.token_store.read_valid_token(
            telegram_identifier
        ) or self.obtain_access_token(telegram_identifier)
        response = self.http_client.request(
            method,
            path,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code == 401:
            self.token_store.delete_access_token(telegram_identifier)
            access_token = self.obtain_access_token(telegram_identifier)
            # Retry only once. A repeated 401 is passed to the presenter.
            response = self.http_client.request(
                method,
                path,
                json=payload,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        response.raise_for_status()
        return response.json() if response.content else None

    def close_client(self):
        self.http_client.close()
        self.token_store.close_storage()

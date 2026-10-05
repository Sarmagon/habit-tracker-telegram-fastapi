import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://habits@database/habits"
    telegram_bot_token: str = ""
    backend_url: str = "http://backend:8000"
    secret_file: str = "/secrets/runtime.json"
    jwt_secret: str = ""
    bot_service_secret: str = ""
    bot_service_secret_hash: str = ""
    bot_token_database_path: str = "/data/tokens.sqlite3"
    bot_token_encryption_key: str = ""
    access_token_minutes: int = Field(default=15, ge=1, le=1440)
    habit_completion_limit: int = Field(default=21, ge=1, le=10000)
    notification_poll_seconds: int = Field(default=15, ge=1, le=300)

    def load_runtime_secrets(self):
        secret_path = Path(self.secret_file)
        if secret_path.exists():
            for secret_name, secret_value in json.loads(
                secret_path.read_text()
            ).items():
                setattr(self, secret_name, secret_value)
        if len(self.jwt_secret) < 32 or not self.bot_service_secret_hash:
            raise RuntimeError("Initialize runtime secrets before starting the backend")
        return self

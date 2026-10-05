import json
import os
import secrets
from pathlib import Path
from urllib.parse import quote

from cryptography.fernet import Fernet
from pwdlib import PasswordHash


def initialize_runtime_secrets():
    directory = Path(os.environ.get("SECRETS_DIRECTORY", "/secrets"))
    directory.mkdir(parents=True, exist_ok=True)
    runtime_path = directory / "runtime.json"
    if runtime_path.exists():
        runtime_secrets = json.loads(runtime_path.read_text(encoding="utf-8"))
    else:
        database_password = secrets.token_urlsafe(32)
        service_secret = secrets.token_urlsafe(48)
        runtime_secrets = {
            "jwt_secret": secrets.token_urlsafe(64),
            "bot_service_secret": service_secret,
            "bot_service_secret_hash": PasswordHash.recommended().hash(service_secret),
            "database_url": f"postgresql+psycopg://habits:{quote(database_password)}@database/habits",
        }
        (directory / "postgres-password").write_text(
            database_password, encoding="utf-8"
        )
    if "bot_token_encryption_key" not in runtime_secrets:
        runtime_secrets["bot_token_encryption_key"] = Fernet.generate_key().decode()
    temporary_path = directory / "runtime.json.tmp"
    temporary_path.write_text(json.dumps(runtime_secrets), encoding="utf-8")
    temporary_path.chmod(0o600)
    temporary_path.replace(runtime_path)
    for secret_path in directory.iterdir():
        secret_path.chmod(0o600)
        if hasattr(os, "chown") and os.geteuid() == 0:
            os.chown(secret_path, 10001, 10001)
    directory.chmod(0o755)
    bot_data_directory = Path(os.environ.get("BOT_DATA_DIRECTORY", "/bot-data"))
    bot_data_directory.mkdir(parents=True, exist_ok=True)
    bot_data_directory.chmod(0o700)
    if hasattr(os, "chown") and os.geteuid() == 0:
        os.chown(bot_data_directory, 10001, 10001)


if __name__ == "__main__":
    initialize_runtime_secrets()

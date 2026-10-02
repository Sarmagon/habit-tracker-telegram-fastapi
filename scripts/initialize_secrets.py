import json
import os
import secrets
from pathlib import Path
from urllib.parse import quote

from pwdlib import PasswordHash


def initialize_runtime_secrets():
    directory = Path(os.environ.get("SECRETS_DIRECTORY", "/secrets"))
    directory.mkdir(parents=True, exist_ok=True)
    runtime_path = directory / "runtime.json"
    if runtime_path.exists():
        return
    database_password = secrets.token_urlsafe(32)
    service_secret = secrets.token_urlsafe(48)
    runtime_secrets = {
        "jwt_secret": secrets.token_urlsafe(64),
        "bot_service_secret": service_secret,
        "bot_service_secret_hash": PasswordHash.recommended().hash(service_secret),
        "database_url": f"postgresql+psycopg://habits:{quote(database_password)}@database/habits",
    }
    (directory / "postgres-password").write_text(database_password)
    runtime_path.write_text(json.dumps(runtime_secrets))
    for secret_path in directory.iterdir():
        secret_path.chmod(0o600)
        if hasattr(os, "chown"):
            os.chown(secret_path, 10001, 10001)
    directory.chmod(0o755)


if __name__ == "__main__":
    initialize_runtime_secrets()

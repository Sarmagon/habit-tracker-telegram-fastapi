import json
import time
from unittest.mock import Mock

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from bot.models.api_client import BackendClient
from bot.models.token_store import TokenStore, UserToken
from common.config import Settings
from scripts.initialize_secrets import initialize_runtime_secrets


@pytest.fixture
def storage_settings(tmp_path):
    return Settings(
        bot_token_database_path=str(tmp_path / "tokens.sqlite3"),
        bot_token_encryption_key=Fernet.generate_key().decode(),
    )


def create_token_store(settings):
    return TokenStore(
        settings.bot_token_database_path, settings.bot_token_encryption_key
    )


def test_storage_survives_restart_and_encrypts_credentials(storage_settings):
    first_store = create_token_store(storage_settings)
    first_store.save_access_token(123, "sensitive-user-access-token", 900)
    with first_store.session_factory() as session:
        record = session.get(UserToken, 123)
        assert b"sensitive-user-access-token" not in record.encrypted_access_token
        assert record.expires_at > time.time()
    first_store.close_storage()
    second_store = create_token_store(storage_settings)
    assert second_store.read_valid_token(123) == "sensitive-user-access-token"
    assert second_store.read_valid_token(999) is None
    second_store.close_storage()


def test_expired_token_is_not_reused_and_next_request_gets_new_token(
    storage_settings, monkeypatch
):
    client = BackendClient(storage_settings)
    client.token_store.save_access_token(123, "old-token", 900)
    future_timestamp = time.time() + 1000
    monkeypatch.setattr("bot.models.token_store.time.time", lambda: future_timestamp)
    client.http_client = Mock()
    client.http_client.post.return_value = Mock()
    client.http_client.post.return_value.json.return_value = {
        "access_token": "new-token",
        "expires_in": 900,
    }
    client.http_client.request.return_value = Mock(status_code=200, content=b"[]")
    client.http_client.request.return_value.json.return_value = []
    assert client.send_request(123, "GET", "/habits") == []
    assert client.token_store.read_valid_token(123) == "new-token"
    assert client.http_client.post.call_count == 1
    client.close_client()


def test_client_reuses_token_after_restart_without_auth_request(storage_settings):
    first_client = BackendClient(storage_settings)
    first_client.token_store.save_access_token(123, "existing-token", 900)
    first_client.close_client()
    second_client = BackendClient(storage_settings)
    second_client.http_client = Mock()
    second_client.http_client.request.return_value = Mock(
        status_code=200, content=b"[]"
    )
    second_client.http_client.request.return_value.json.return_value = []
    assert second_client.send_request(123, "GET", "/habits") == []
    second_client.http_client.post.assert_not_called()
    second_client.close_client()


def test_wrong_key_or_corrupt_ciphertext_requires_reauthentication(storage_settings):
    first_store = create_token_store(storage_settings)
    first_store.save_access_token(123, "original-token", 900)
    first_store.close_storage()
    second_store = TokenStore(
        storage_settings.bot_token_database_path, Fernet.generate_key().decode()
    )
    assert second_store.read_valid_token(123) is None
    with second_store.session_factory() as session:
        assert session.get(UserToken, 123) is None
    second_store.close_storage()


def test_repeated_unauthorized_does_not_loop(storage_settings):
    client = BackendClient(storage_settings)
    client.token_store.save_access_token(123, "rejected-token", 900)
    client.http_client = Mock()
    client.http_client.post.return_value.json.return_value = {
        "access_token": "new-token",
        "expires_in": 900,
    }
    request = httpx.Request("GET", "http://backend/api/v1/habits")
    response = httpx.Response(401, json={"detail": "Unauthorized"}, request=request)
    client.http_client.request.return_value = response
    with pytest.raises(httpx.HTTPStatusError):
        client.send_request(123, "GET", "/habits")
    assert client.http_client.request.call_count == 2
    assert client.http_client.post.call_count == 1
    client.close_client()


def test_token_updates_replace_existing_row(storage_settings):
    store = create_token_store(storage_settings)
    store.save_access_token(123, "first-token", 900)
    store.save_access_token(123, "second-token", 900)
    assert store.read_valid_token(123) == "second-token"
    with store.session_factory() as session:
        assert len(session.scalars(select(UserToken)).all()) == 1
    store.close_storage()


def test_bootstrap_upgrade_preserves_existing_credentials(tmp_path, monkeypatch):
    secret_directory = tmp_path / "secrets"
    secret_directory.mkdir()
    prior_credentials = {
        "jwt_secret": "existing-jwt-secret",
        "bot_service_secret": "existing-service-secret",
        "bot_service_secret_hash": "existing-hash",
        "database_url": "existing-database-url",
    }
    (secret_directory / "runtime.json").write_text(json.dumps(prior_credentials))
    monkeypatch.setenv("SECRETS_DIRECTORY", str(secret_directory))
    monkeypatch.setenv("BOT_DATA_DIRECTORY", str(tmp_path / "bot-data"))
    initialize_runtime_secrets()
    result = json.loads((secret_directory / "runtime.json").read_text())
    assert all(result[name] == value for name, value in prior_credentials.items())
    Fernet(result["bot_token_encryption_key"].encode())
    initialize_runtime_secrets()
    assert json.loads((secret_directory / "runtime.json").read_text()) == result

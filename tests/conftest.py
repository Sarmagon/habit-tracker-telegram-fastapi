import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-jwt-secret-at-least-thirty-two-characters"
os.environ["SECRET_FILE"] = "nonexistent-test-secret.json"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.controllers import routes
from backend.database import open_database_session
from backend.main import application
from backend.models.entities import Base, User
from backend.services.security import create_access_token, password_hasher
from common.config import Settings


@pytest.fixture
def database_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, connection_record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def user(database_session):
    user = User(telegram_identifier=123456, timezone_name="Europe/Moscow")
    database_session.add(user)
    database_session.commit()
    return user


@pytest.fixture
def client(database_session, monkeypatch):
    def override_database_session():
        yield database_session

    test_settings = Settings(
        bot_service_secret_hash=password_hasher.hash("test-secret")
    )
    monkeypatch.setattr(routes, "load_security_settings", lambda: test_settings)
    application.dependency_overrides[open_database_session] = override_database_session
    test_client = TestClient(application)
    yield test_client
    test_client.close()
    application.dependency_overrides.clear()


@pytest.fixture
def authorization_headers(user):
    return {
        "Authorization": "Bearer " + create_access_token(user.identifier, Settings())
    }

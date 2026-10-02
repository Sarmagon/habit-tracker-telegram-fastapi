from datetime import UTC, datetime, timedelta

import jwt
import pytest

from backend.models.entities import User
from common.config import Settings


def create_payload():
    return {"title": "Читать", "description": "10 страниц", "start_date": "2026-01-01"}


def test_authentication_is_required(client):
    assert client.get("/api/v1/habits").status_code == 401


@pytest.mark.parametrize(
    "path,method",
    [
        ("/habits/1", "PUT"),
        ("/habits/1", "DELETE"),
        ("/habits/1/completion", "POST"),
        ("/habits/1/history", "GET"),
    ],
)
def test_cross_user_access_is_denied(
    client, database_session, user, authorization_headers, path, method
):
    response = client.post(
        "/api/v1/habits", json=create_payload(), headers=authorization_headers
    )
    assert response.status_code == 201
    other_user = User(telegram_identifier=999999)
    database_session.add(other_user)
    database_session.commit()
    from backend.services.security import create_access_token

    headers = {
        "Authorization": "Bearer "
        + create_access_token(other_user.identifier, Settings())
    }
    payload = (
        {"completed": True, "record_date": "2026-10-02"}
        if "completion" in path
        else create_payload()
    )
    response = client.request(method, "/api/v1" + path, json=payload, headers=headers)
    assert response.status_code == 404


def test_crud_and_history(client, authorization_headers):
    response = client.post(
        "/api/v1/habits", json=create_payload(), headers=authorization_headers
    )
    habit_identifier = response.json()["identifier"]
    path = f"/api/v1/habits/{habit_identifier}"
    payload = create_payload() | {"title": "Читать книгу"}
    assert (
        client.put(path, json=payload, headers=authorization_headers).json()["title"]
        == "Читать книгу"
    )
    habits = client.get("/api/v1/habits", headers=authorization_headers).json()
    assert habits[0]["completed"] is None
    completion = {"completed": True, "record_date": habits[0]["record_date"]}
    assert (
        client.post(
            path + "/completion", json=completion, headers=authorization_headers
        ).status_code
        == 200
    )
    assert (
        client.get(path + "/history", headers=authorization_headers).json()[0][
            "completed"
        ]
        is True
    )
    assert client.delete(path, headers=authorization_headers).status_code == 204
    assert (
        client.get(path + "/history", headers=authorization_headers).status_code == 404
    )


def test_rejects_expired_and_tampered_tokens(client, user):
    claims = {
        "sub": str(user.identifier),
        "iat": datetime.now(UTC) - timedelta(hours=2),
        "exp": datetime.now(UTC) - timedelta(hours=1),
        "iss": "habit-tracker",
        "aud": "habit-api",
    }
    token = jwt.encode(claims, Settings().jwt_secret, algorithm="HS256")
    assert (
        client.get(
            "/api/v1/habits", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 401
    )
    claims["exp"] = datetime.now(UTC) + timedelta(hours=1)
    token = jwt.encode(
        claims, "wrong-signing-key-that-is-long-enough", algorithm="HS256"
    )
    assert (
        client.get(
            "/api/v1/habits", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "  ", "start_date": "2026-01-01"},
        {"title": "Read", "start_date": "2026-01-02", "end_date": "2026-01-01"},
    ],
)
def test_rejects_invalid_habit_input(client, authorization_headers, payload):
    assert (
        client.post(
            "/api/v1/habits", json=payload, headers=authorization_headers
        ).status_code
        == 422
    )


def test_rejects_unknown_timezone(client, authorization_headers):
    payload = {"timezone_name": "Unknown/Timezone", "reminder_time": "20:00"}
    assert (
        client.put(
            "/api/v1/settings/reminder", json=payload, headers=authorization_headers
        ).status_code
        == 422
    )


def test_untrusted_bot_cannot_impersonate_telegram_user(client):
    response = client.post(
        "/api/v1/auth/telegram",
        json={"telegram_identifier": 123456},
        headers={"X-Bot-Service-Secret": "wrong-service-secret"},
    )
    assert response.status_code == 401


def test_trusted_bot_receives_user_token(client):
    response = client.post(
        "/api/v1/auth/telegram",
        json={"telegram_identifier": 123456},
        headers={"X-Bot-Service-Secret": "test-secret"},
    )
    assert response.status_code == 200
    access_token = response.json()["access_token"]
    response = client.get(
        "/api/v1/habits", headers={"Authorization": "Bearer " + access_token}
    )
    assert response.status_code == 200

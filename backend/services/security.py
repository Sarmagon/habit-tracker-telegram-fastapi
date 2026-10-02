from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException
from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()


def create_access_token(user_identifier, settings):
    issued_at = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_identifier),
            "iat": issued_at,
            "exp": issued_at + timedelta(minutes=settings.access_token_minutes),
            "iss": "habit-tracker",
            "aud": "habit-api",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_access_token(access_token, settings):
    try:
        payload = jwt.decode(
            access_token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience="habit-api",
            issuer="habit-tracker",
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
        return int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError) as error:
        raise HTTPException(
            401, "Недействительный токен", headers={"WWW-Authenticate": "Bearer"}
        ) from error

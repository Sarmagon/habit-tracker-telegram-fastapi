from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.database import open_database_session
from backend.models.entities import DailyRecord, Habit, User
from backend.schemas.contracts import (
    CompletionInput,
    HabitInput,
    HabitOutput,
    ReminderInput,
    TelegramIdentity,
)
from backend.services.habits import (
    get_owned_habit,
    list_habits,
    lock_user,
    mark_completion,
)
from backend.services.security import (
    create_access_token,
    decode_access_token,
    password_hasher,
)
from common.config import Settings

router = APIRouter()
DatabaseSession = Annotated[Session, Depends(open_database_session)]
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="UserAccessToken",
    bearerFormat="JWT",
    description=(
        "JWT пользователя. Получите токен через доверенного бота или CLI. "
        "В Authorize вставьте только JWT, без префикса Bearer."
    ),
)


def load_security_settings():
    return Settings().load_runtime_secrets()


def authenticate_user(
    database_session: DatabaseSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
):
    if credentials is None:
        raise HTTPException(401, "Требуется токен")
    user_identifier = decode_access_token(
        credentials.credentials, load_security_settings()
    )
    user = lock_user(database_session, user_identifier)
    if user is None:
        raise HTTPException(401, "Пользователь не найден")
    return user


CurrentUser = Annotated[User, Depends(authenticate_user)]


@router.post("/auth/telegram")
def authenticate_telegram(
    identity: TelegramIdentity,
    database_session: DatabaseSession,
    service_secret: Annotated[str, Header(alias="X-Bot-Service-Secret")],
):
    settings = load_security_settings()
    if not password_hasher.verify(service_secret, settings.bot_service_secret_hash):
        raise HTTPException(401, "Бот не авторизован")
    database_session.execute(
        insert(User)
        .values(telegram_identifier=identity.telegram_identifier)
        .on_conflict_do_nothing(index_elements=[User.telegram_identifier])
    )
    user = database_session.scalar(
        select(User).where(User.telegram_identifier == identity.telegram_identifier)
    )
    database_session.commit()
    return {
        "access_token": create_access_token(user.identifier, settings),
        "token_type": "bearer",
        "expires_in": settings.access_token_minutes * 60,
    }


@router.get("/habits", response_model=list[HabitOutput])
def read_habits(
    database_session: DatabaseSession, user: CurrentUser, include_archive: bool = False
):
    results = list_habits(
        database_session, user, Settings().habit_completion_limit, include_archive
    )
    database_session.commit()
    return results


@router.post("/habits", response_model=HabitOutput, status_code=201)
def create_habit(
    payload: HabitInput, database_session: DatabaseSession, user: CurrentUser
):
    habit = Habit(owner_identifier=user.identifier, **payload.model_dump())
    database_session.add(habit)
    database_session.commit()
    database_session.refresh(habit)
    return habit


@router.put("/habits/{habit_identifier}", response_model=HabitOutput)
def update_habit(
    habit_identifier: int,
    payload: HabitInput,
    database_session: DatabaseSession,
    user: CurrentUser,
):
    habit = get_owned_habit(database_session, user.identifier, habit_identifier)
    for field_name, field_value in payload.model_dump().items():
        setattr(habit, field_name, field_value)
    database_session.commit()
    return habit


@router.delete("/habits/{habit_identifier}", status_code=204)
def delete_habit(
    habit_identifier: int, database_session: DatabaseSession, user: CurrentUser
):
    database_session.delete(
        get_owned_habit(database_session, user.identifier, habit_identifier)
    )
    database_session.commit()


@router.post("/habits/{habit_identifier}/completion", response_model=HabitOutput)
def record_completion(
    habit_identifier: int,
    payload: CompletionInput,
    database_session: DatabaseSession,
    user: CurrentUser,
):
    habit = mark_completion(
        database_session,
        user,
        habit_identifier,
        payload.completed,
        payload.record_date,
        Settings().habit_completion_limit,
    )
    database_session.commit()
    result = HabitOutput.model_validate(habit)
    result.completed = payload.completed
    result.record_date = payload.record_date
    result.archived = habit.completion_count >= Settings().habit_completion_limit
    return result


@router.get("/habits/{habit_identifier}/history")
def read_habit_history(
    habit_identifier: int, database_session: DatabaseSession, user: CurrentUser
):
    get_owned_habit(database_session, user.identifier, habit_identifier)
    records = database_session.scalars(
        select(DailyRecord)
        .where(DailyRecord.habit_identifier == habit_identifier)
        .order_by(DailyRecord.record_date.desc())
        .limit(100)
    ).all()
    return [
        {"record_date": record.record_date, "completed": record.completed}
        for record in records
    ]


@router.put("/settings/reminder")
def update_reminder(
    payload: ReminderInput, database_session: DatabaseSession, user: CurrentUser
):
    for field_name, field_value in payload.model_dump().items():
        setattr(user, field_name, field_value)
    database_session.commit()
    return payload


@router.get("/profile")
def read_profile(user: CurrentUser):
    return {
        "timezone_name": user.timezone_name,
        "reminder_time": user.reminder_time,
        "reminders_enabled": user.reminders_enabled,
    }

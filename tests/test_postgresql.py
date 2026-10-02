"""Opt-in checks against a disposable PostgreSQL schema, including row locks."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.models.entities import Base, Habit, User
from backend.services.habits import get_local_date, lock_user, mark_completion


@pytest.fixture
def postgresql_factory():
    database_url = os.environ.get("POSTGRES_TEST_URL")
    if not database_url:
        pytest.skip("POSTGRES_TEST_URL is not set")
    schema_name = "habit_test_" + uuid.uuid4().hex
    administration_engine = create_engine(database_url)
    with administration_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
    engine = create_engine(
        database_url, connect_args={"options": f"-csearch_path={schema_name}"}
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()
        with administration_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        administration_engine.dispose()


def test_concurrent_marks_do_not_double_count(postgresql_factory):
    with postgresql_factory() as session:
        user = User(telegram_identifier=123)
        session.add(user)
        session.flush()
        habit = Habit(
            owner_identifier=user.identifier,
            title="Read",
            start_date=get_local_date(user),
        )
        session.add(habit)
        session.commit()
        user_identifier, habit_identifier = user.identifier, habit.identifier

    def mark_today(_):
        with postgresql_factory() as session:
            user = lock_user(session, user_identifier)
            mark_completion(
                session, user, habit_identifier, True, get_local_date(user), 21
            )
            session.commit()

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(mark_today, range(16)))
    with postgresql_factory() as session:
        assert session.get(Habit, habit_identifier).completion_count == 1

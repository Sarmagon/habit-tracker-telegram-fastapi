import os
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

from backend.models.entities import Base
from common.config import Settings

configuration = context.config

settings = Settings()
if os.environ.get("DATABASE_URL"):
    connection_url = settings.database_url
elif Path(settings.secret_file).exists():
    connection_url = settings.load_runtime_secrets().database_url
else:
    connection_url = settings.database_url


def run_migrations_offline():
    context.configure(
        url=connection_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(connection_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

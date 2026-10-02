from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.config import Settings

settings = Settings()
database_engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionFactory = sessionmaker(database_engine, expire_on_commit=False)


def open_database_session():
    with SessionFactory() as database_session:
        yield database_session

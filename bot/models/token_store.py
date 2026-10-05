import os
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import BigInteger, Float, Integer, LargeBinary, create_engine, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class TokenBase(DeclarativeBase):
    pass


class UserToken(TokenBase):
    __tablename__ = "user_tokens"
    telegram_identifier: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    encrypted_access_token: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)


class TokenSchemaVersion(TokenBase):
    __tablename__ = "token_schema_version"
    identifier: Mapped[int] = mapped_column(Integer, primary_key=True)


class TokenStore:
    """Bot-owned encrypted SQLite storage, independent of backend PostgreSQL."""

    def __init__(self, database_path, encryption_key):
        if not encryption_key:
            raise RuntimeError("Initialize the bot token encryption key first")
        self.cipher = Fernet(encryption_key.encode())
        database_path = Path(database_path)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            "sqlite:///" + str(database_path.resolve()),
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        TokenBase.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        with self.session_factory.begin() as database_session:
            if database_session.get(TokenSchemaVersion, 1) is None:
                database_session.add(TokenSchemaVersion(identifier=1))
        database_path.chmod(0o600)
        if os.name != "nt":
            database_path.parent.chmod(0o700)

    def read_valid_token(self, telegram_identifier, current_time=None):
        current_time = time.time() if current_time is None else current_time
        with self.session_factory() as database_session:
            token_record = database_session.get(UserToken, telegram_identifier)
            if token_record is None:
                return None
            if token_record.expires_at <= current_time + 30:
                return None
            try:
                return self.cipher.decrypt(token_record.encrypted_access_token).decode()
            except (InvalidToken, UnicodeDecodeError):
                # Corrupt ciphertext or a changed encryption key requires re-auth.
                database_session.delete(token_record)
                database_session.commit()
                return None

    def save_access_token(self, telegram_identifier, access_token, expires_in):
        updated_at = time.time()
        values = {
            "telegram_identifier": telegram_identifier,
            "encrypted_access_token": self.cipher.encrypt(access_token.encode()),
            "expires_at": updated_at + expires_in,
            "updated_at": updated_at,
        }
        with self.session_factory.begin() as database_session:
            database_session.execute(
                insert(UserToken)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[UserToken.telegram_identifier],
                    set_=values,
                )
            )
            # Expired credentials are not needed; keep storage bounded by active users.
            expired_records = database_session.scalars(
                select(UserToken).where(UserToken.expires_at <= updated_at)
            ).all()
            for token_record in expired_records:
                database_session.delete(token_record)

    def delete_access_token(self, telegram_identifier):
        with self.session_factory.begin() as database_session:
            token_record = database_session.get(UserToken, telegram_identifier)
            if token_record is not None:
                database_session.delete(token_record)

    def close_storage(self):
        self.engine.dispose()

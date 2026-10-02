"""Create users, habits and immutable daily record identities."""

import sqlalchemy as sqlalchemy
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sqlalchemy.Column("identifier", sqlalchemy.Integer(), primary_key=True),
        sqlalchemy.Column(
            "telegram_identifier", sqlalchemy.BigInteger(), nullable=False, unique=True
        ),
        sqlalchemy.Column("timezone_name", sqlalchemy.String(64), nullable=False),
        sqlalchemy.Column("reminder_time", sqlalchemy.Time(), nullable=False),
        sqlalchemy.Column("last_reminder_date", sqlalchemy.Date(), nullable=True),
        sqlalchemy.Column(
            "next_reminder_attempt", sqlalchemy.BigInteger(), nullable=False
        ),
        sqlalchemy.Column("reminders_enabled", sqlalchemy.Boolean(), nullable=False),
    )
    op.create_table(
        "habits",
        sqlalchemy.Column("identifier", sqlalchemy.Integer(), primary_key=True),
        sqlalchemy.Column(
            "owner_identifier",
            sqlalchemy.Integer(),
            sqlalchemy.ForeignKey("users.identifier", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("title", sqlalchemy.String(120), nullable=False),
        sqlalchemy.Column("description", sqlalchemy.String(1000), nullable=False),
        sqlalchemy.Column("start_date", sqlalchemy.Date(), nullable=False),
        sqlalchemy.Column("end_date", sqlalchemy.Date(), nullable=True),
        sqlalchemy.Column("completion_count", sqlalchemy.Integer(), nullable=False),
        sqlalchemy.CheckConstraint("completion_count >= 0"),
    )
    op.create_index("ix_habits_owner_identifier", "habits", ["owner_identifier"])
    op.create_table(
        "daily_records",
        sqlalchemy.Column("identifier", sqlalchemy.Integer(), primary_key=True),
        sqlalchemy.Column(
            "habit_identifier",
            sqlalchemy.Integer(),
            sqlalchemy.ForeignKey("habits.identifier", ondelete="CASCADE"),
            nullable=False,
        ),
        sqlalchemy.Column("record_date", sqlalchemy.Date(), nullable=False),
        sqlalchemy.Column("completed", sqlalchemy.Boolean(), nullable=True),
        sqlalchemy.UniqueConstraint("habit_identifier", "record_date"),
    )
    op.create_index(
        "ix_daily_records_habit_identifier", "daily_records", ["habit_identifier"]
    )


def downgrade():
    op.drop_table("daily_records")
    op.drop_table("habits")
    op.drop_table("users")

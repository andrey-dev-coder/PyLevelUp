"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-05-04

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("language_code", sa.String(length=8), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_active_date", sa.Date(), nullable=True),
        sa.Column("total_correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_answered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ranking_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_ranking_position", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("reminders_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=False)

    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=64), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correct_index", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("external_key", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_questions"),
        sa.UniqueConstraint("external_key", name="uq_questions_external_key"),
    )
    op.create_index("ix_questions_topic", "questions", ["topic"], unique=False)

    op.create_table(
        "user_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("ease_factor", sa.Float(), nullable=False, server_default="2.5"),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_review_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_quality", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_progress_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name="fk_user_progress_question_id_questions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_progress"),
        sa.UniqueConstraint("user_id", "question_id", name="uq_user_progress_user_question"),
    )
    op.create_index("ix_user_progress_user_id", "user_progress", ["user_id"], unique=False)
    op.create_index("ix_user_progress_question_id", "user_progress", ["question_id"], unique=False)
    op.create_index("ix_user_progress_due", "user_progress", ["user_id", "next_review_at"], unique=False)

    op.create_table(
        "attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("quality", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_attempts_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name="fk_attempts_question_id_questions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attempts"),
    )
    op.create_index("ix_attempts_user_id", "attempts", ["user_id"], unique=False)
    op.create_index("ix_attempts_question_id", "attempts", ["question_id"], unique=False)
    op.create_index("ix_attempts_session_date", "attempts", ["session_date"], unique=False)
    op.create_index(
        "ix_attempts_user_session_date", "attempts", ["user_id", "session_date"], unique=False
    )

    op.create_table(
        "daily_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("questions_answered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("finished", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_daily_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_daily_sessions"),
        sa.UniqueConstraint("user_id", "session_date", name="uq_daily_sessions_user_date"),
    )
    op.create_index("ix_daily_sessions_user_id", "daily_sessions", ["user_id"], unique=False)
    op.create_index("ix_daily_sessions_session_date", "daily_sessions", ["session_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_daily_sessions_session_date", table_name="daily_sessions")
    op.drop_index("ix_daily_sessions_user_id", table_name="daily_sessions")
    op.drop_table("daily_sessions")

    op.drop_index("ix_attempts_user_session_date", table_name="attempts")
    op.drop_index("ix_attempts_session_date", table_name="attempts")
    op.drop_index("ix_attempts_question_id", table_name="attempts")
    op.drop_index("ix_attempts_user_id", table_name="attempts")
    op.drop_table("attempts")

    op.drop_index("ix_user_progress_due", table_name="user_progress")
    op.drop_index("ix_user_progress_question_id", table_name="user_progress")
    op.drop_index("ix_user_progress_user_id", table_name="user_progress")
    op.drop_table("user_progress")

    op.drop_index("ix_questions_topic", table_name="questions")
    op.drop_table("questions")

    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")

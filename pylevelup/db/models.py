from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pylevelup.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    total_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_answered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_starts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    ranking_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_ranking_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    hints_used_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hints_reset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_digest_sent_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    progress: Mapped[list["UserProgress"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="raise"
    )
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="raise"
    )
    sessions: Mapped[list["DailySession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="raise"
    )


class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    options: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    option_explanations: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    external_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UserProgress(Base, TimestampMixin):
    __tablename__ = "user_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_user_progress_user_question"),
        Index("ix_user_progress_due", "user_id", "next_review_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    ease_factor: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    next_review_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped[User] = relationship(back_populates="progress", lazy="raise")
    question: Mapped[Question] = relationship(lazy="raise")


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        Index("ix_attempts_user_session_date", "user_id", "session_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    user: Mapped[User] = relationship(back_populates="attempts", lazy="raise")
    question: Mapped[Question] = relationship(lazy="raise")


class BotSetting(Base, TimestampMixin):
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class DailySession(Base, TimestampMixin):
    __tablename__ = "daily_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "session_date", name="uq_daily_sessions_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    questions_answered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finished: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions", lazy="raise")


class Bookmark(Base, TimestampMixin):
    __tablename__ = "bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_bookmarks_user_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )


class Achievement(Base, TimestampMixin):
    __tablename__ = "achievements"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(String(8), nullable=False, default="⭐")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (
        UniqueConstraint("user_id", "achievement_code", name="uq_user_achievements_user_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    achievement_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("achievements.code", ondelete="CASCADE"), nullable=False, index=True
    )
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DailyChallenge(Base, TimestampMixin):
    __tablename__ = "daily_challenges"

    challenge_date: Mapped[date] = mapped_column(Date, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class DailyChallengeAttempt(Base):
    __tablename__ = "daily_challenge_attempts"
    __table_args__ = (
        UniqueConstraint("user_id", "challenge_date", name="uq_dca_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    challenge_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MockSession(Base, TimestampMixin):
    __tablename__ = "mock_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class QuestionReport(Base, TimestampMixin):
    __tablename__ = "question_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccessCode(Base, TimestampMixin):
    __tablename__ = "access_codes"

    code: Mapped[str] = mapped_column(String(128), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed_topics: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class UserTopicAccess(Base):
    __tablename__ = "user_topic_access"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    topic_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CustomCategory(Base, TimestampMixin):
    __tablename__ = "custom_categories"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    short: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class AIUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (
        Index("ix_ai_usage_user_date", "user_id", "usage_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OpenQuestion(Base, TimestampMixin):
    __tablename__ = "open_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    topic: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ideal_answer: Mapped[str] = mapped_column(Text, nullable=False)
    checklist: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class LearningPath(Base, TimestampMixin):
    __tablename__ = "learning_paths"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    steps: Mapped[list["LearningPathStep"]] = relationship(
        "LearningPathStep",
        back_populates="path",
        cascade="all, delete-orphan",
        order_by="LearningPathStep.position",
    )


class LearningPathStep(Base):
    __tablename__ = "learning_path_steps"
    __table_args__ = (
        UniqueConstraint("path_id", "position", name="uq_path_step_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    required_accuracy: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    required_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    path: Mapped["LearningPath"] = relationship("LearningPath", back_populates="steps")


class UserLearningPathProgress(Base):
    __tablename__ = "user_learning_path_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "path_id", name="uq_user_path"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import Attempt, Question, User


@dataclass
class TopicStats:
    topic: str
    answered: int
    correct: int

    @property
    def accuracy_percent(self) -> float:
        return round(self.correct / self.answered * 100.0, 1) if self.answered else 0.0


@dataclass
class UserStats:
    current_streak: int
    max_streak: int
    total_correct: int
    total_answered: int
    accuracy_percent: float
    ranking_position: int | None
    ranking_score: float
    total_users: int
    total_starts: int
    last_active_date: date | None
    member_since: date | None
    mistakes_count: int
    topics: list[TopicStats] = field(default_factory=list)


class StatsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_stats(self, user_id: int) -> UserStats | None:
        ranked = (
            select(
                User.id.label("user_id"),
                User.current_streak,
                User.max_streak,
                User.total_correct,
                User.total_answered,
                User.ranking_score,
                func.rank()
                .over(order_by=(User.ranking_score.desc(), User.total_correct.desc()))
                .label("position"),
            )
            .where(User.is_active.is_(True))
            .subquery()
        )

        total_users_stmt = select(func.count(User.id)).where(User.is_active.is_(True))
        total_users = int((await self.session.execute(total_users_stmt)).scalar_one())

        stmt = select(ranked).where(ranked.c.user_id == user_id)
        row = (await self.session.execute(stmt)).one_or_none()
        if row is None:
            return None

        accuracy = (row.total_correct / row.total_answered * 100.0) if row.total_answered else 0.0

        user_obj = await self.session.get(User, user_id)

        topic_stmt = (
            select(
                Question.topic.label("topic"),
                func.count(Attempt.id).label("answered"),
                func.sum(case((Attempt.is_correct.is_(True), 1), else_=0)).label("correct"),
            )
            .join(Question, Question.id == Attempt.question_id)
            .where(Attempt.user_id == user_id)
            .group_by(Question.topic)
        )
        topic_rows = (await self.session.execute(topic_stmt)).all()
        topics = [
            TopicStats(
                topic=str(r.topic),
                answered=int(r.answered or 0),
                correct=int(r.correct or 0),
            )
            for r in topic_rows
        ]
        topics.sort(key=lambda t: (-t.answered, t.topic))

        mistakes_stmt = (
            select(func.count(func.distinct(Attempt.question_id)))
            .where(Attempt.user_id == user_id, Attempt.is_correct.is_(False))
        )
        mistakes_count = int((await self.session.execute(mistakes_stmt)).scalar_one() or 0)

        return UserStats(
            current_streak=row.current_streak,
            max_streak=row.max_streak,
            total_correct=row.total_correct,
            total_answered=row.total_answered,
            accuracy_percent=round(accuracy, 1),
            ranking_position=int(row.position),
            ranking_score=round(float(row.ranking_score), 2),
            total_users=total_users,
            total_starts=int(user_obj.total_starts) if user_obj else 0,
            last_active_date=user_obj.last_active_date if user_obj else None,
            member_since=user_obj.created_at.date() if user_obj and user_obj.created_at else None,
            mistakes_count=mistakes_count,
            topics=topics,
        )

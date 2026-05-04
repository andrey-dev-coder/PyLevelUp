from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import User


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
        return UserStats(
            current_streak=row.current_streak,
            max_streak=row.max_streak,
            total_correct=row.total_correct,
            total_answered=row.total_answered,
            accuracy_percent=round(accuracy, 1),
            ranking_position=int(row.position),
            ranking_score=round(float(row.ranking_score), 2),
            total_users=total_users,
        )

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import User


class RankingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def recompute_global_ranking(self) -> int:
        accuracy = case(
            (User.total_answered > 0, User.total_correct * 1.0 / User.total_answered),
            else_=0.0,
        )
        score_expr = (
            User.total_correct * 1.0
            + accuracy * 50.0
            + User.current_streak * 5.0
            + User.max_streak * 2.0
        )

        ranked = (
            select(
                User.id.label("user_id"),
                score_expr.label("score"),
                func.rank().over(order_by=score_expr.desc()).label("position"),
            )
            .where(User.is_active.is_(True))
            .subquery()
        )

        stmt = (
            update(User)
            .where(User.id == ranked.c.user_id)
            .values(ranking_score=ranked.c.score, last_ranking_position=ranked.c.position)
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import UserAchievement


class AchievementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_codes(self, user_id: int) -> set[str]:
        stmt = select(UserAchievement.achievement_code).where(
            UserAchievement.user_id == user_id
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return set(rows)

    async def grant(self, user_id: int, code: str) -> bool:
        stmt = (
            pg_insert(UserAchievement)
            .values(user_id=user_id, achievement_code=code)
            .on_conflict_do_nothing(
                index_elements=[
                    UserAchievement.user_id,
                    UserAchievement.achievement_code,
                ]
            )
            .returning(UserAchievement.id)
        )
        result = (await self.session.execute(stmt)).scalar_one_or_none()
        return result is not None


__all__ = ["AchievementRepository"]

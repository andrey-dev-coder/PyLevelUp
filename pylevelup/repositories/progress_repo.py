from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import UserProgress


class ProgressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int, question_id: int) -> UserProgress | None:
        stmt = select(UserProgress).where(
            UserProgress.user_id == user_id,
            UserProgress.question_id == question_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self,
        user_id: int,
        question_id: int,
        ease_factor: float,
        interval_days: int,
        repetitions: int,
        next_review_at: datetime,
        last_quality: int,
    ) -> None:
        stmt = (
            insert(UserProgress)
            .values(
                user_id=user_id,
                question_id=question_id,
                ease_factor=ease_factor,
                interval_days=interval_days,
                repetitions=repetitions,
                next_review_at=next_review_at,
                last_reviewed_at=datetime.now(UTC),
                last_quality=last_quality,
            )
            .on_conflict_do_update(
                constraint="uq_user_progress_user_question",
                set_={
                    "ease_factor": ease_factor,
                    "interval_days": interval_days,
                    "repetitions": repetitions,
                    "next_review_at": next_review_at,
                    "last_reviewed_at": datetime.now(UTC),
                    "last_quality": last_quality,
                },
            )
        )
        await self.session.execute(stmt)

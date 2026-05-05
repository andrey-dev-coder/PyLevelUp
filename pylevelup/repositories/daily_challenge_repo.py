from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import (
    DailyChallenge,
    DailyChallengeAttempt,
    User,
)


class DailyChallengeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_date(self, challenge_date: date) -> DailyChallenge | None:
        return await self.session.get(DailyChallenge, challenge_date)

    async def upsert_for_date(self, challenge_date: date, question_id: int) -> DailyChallenge:
        stmt = (
            pg_insert(DailyChallenge)
            .values(challenge_date=challenge_date, question_id=question_id)
            .on_conflict_do_nothing(index_elements=[DailyChallenge.challenge_date])
        )
        await self.session.execute(stmt)
        await self.session.flush()
        existing = await self.session.get(DailyChallenge, challenge_date)
        if existing is None:
            raise RuntimeError("daily_challenge_upsert_failed")
        return existing

    async def has_attempted(self, user_id: int, challenge_date: date) -> bool:
        stmt = select(DailyChallengeAttempt.id).where(
            DailyChallengeAttempt.user_id == user_id,
            DailyChallengeAttempt.challenge_date == challenge_date,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def get_attempt(
        self, user_id: int, challenge_date: date
    ) -> DailyChallengeAttempt | None:
        stmt = select(DailyChallengeAttempt).where(
            DailyChallengeAttempt.user_id == user_id,
            DailyChallengeAttempt.challenge_date == challenge_date,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def record_attempt(
        self,
        user_id: int,
        challenge_date: date,
        is_correct: bool,
        response_time_ms: int | None,
    ) -> bool:
        stmt = (
            pg_insert(DailyChallengeAttempt)
            .values(
                user_id=user_id,
                challenge_date=challenge_date,
                is_correct=is_correct,
                response_time_ms=response_time_ms,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    DailyChallengeAttempt.user_id,
                    DailyChallengeAttempt.challenge_date,
                ]
            )
            .returning(DailyChallengeAttempt.id)
        )
        result = (await self.session.execute(stmt)).scalar_one_or_none()
        await self.session.flush()
        return result is not None

    async def list_top_correct(
        self, challenge_date: date, limit: int = 10
    ) -> list[tuple[User, int | None]]:
        stmt = (
            select(User, DailyChallengeAttempt.response_time_ms)
            .join(DailyChallengeAttempt, DailyChallengeAttempt.user_id == User.id)
            .where(
                DailyChallengeAttempt.challenge_date == challenge_date,
                DailyChallengeAttempt.is_correct.is_(True),
            )
            .order_by(
                DailyChallengeAttempt.response_time_ms.is_(None),
                DailyChallengeAttempt.response_time_ms.asc(),
                DailyChallengeAttempt.answered_at.asc(),
            )
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]

    async def stats(self, challenge_date: date) -> tuple[int, int]:
        total_stmt = select(func.count(DailyChallengeAttempt.id)).where(
            DailyChallengeAttempt.challenge_date == challenge_date
        )
        correct_stmt = select(func.count(DailyChallengeAttempt.id)).where(
            DailyChallengeAttempt.challenge_date == challenge_date,
            DailyChallengeAttempt.is_correct.is_(True),
        )
        total = int((await self.session.execute(total_stmt)).scalar_one())
        correct = int((await self.session.execute(correct_stmt)).scalar_one())
        return total, correct

    async def user_rank(self, challenge_date: date, user_id: int) -> int | None:
        own = await self.get_attempt(user_id, challenge_date)
        if own is None or not own.is_correct:
            return None
        all_correct_stmt = (
            select(DailyChallengeAttempt)
            .where(
                DailyChallengeAttempt.challenge_date == challenge_date,
                DailyChallengeAttempt.is_correct.is_(True),
            )
            .order_by(
                DailyChallengeAttempt.response_time_ms.is_(None),
                DailyChallengeAttempt.response_time_ms.asc(),
                DailyChallengeAttempt.answered_at.asc(),
            )
        )
        rows = list((await self.session.execute(all_correct_stmt)).scalars().all())
        for index, attempt in enumerate(rows, start=1):
            if attempt.user_id == user_id:
                return index
        return None


__all__ = ["DailyChallengeRepository"]

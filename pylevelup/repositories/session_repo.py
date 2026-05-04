from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import DailySession


class DailySessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int, session_date: date) -> DailySession | None:
        stmt = select(DailySession).where(
            DailySession.user_id == user_id,
            DailySession.session_date == session_date,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self,
        user_id: int,
        session_date: date,
        questions_answered: int,
        correct_count: int,
        finished: bool,
    ) -> None:
        finished_at = datetime.now(UTC) if finished else None
        stmt = (
            insert(DailySession)
            .values(
                user_id=user_id,
                session_date=session_date,
                questions_answered=questions_answered,
                correct_count=correct_count,
                finished=finished,
                finished_at=finished_at,
            )
            .on_conflict_do_update(
                constraint="uq_daily_sessions_user_date",
                set_={
                    "questions_answered": questions_answered,
                    "correct_count": correct_count,
                    "finished": finished,
                    "finished_at": finished_at,
                },
            )
        )
        await self.session.execute(stmt)

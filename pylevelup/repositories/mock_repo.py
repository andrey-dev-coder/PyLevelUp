from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import MockSession


class MockSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: int,
        total_questions: int,
        correct_count: int,
        duration_seconds: int,
        breakdown: dict[str, Any],
        passed: bool,
        finished_at: datetime,
    ) -> MockSession:
        record = MockSession(
            user_id=user_id,
            total_questions=total_questions,
            correct_count=correct_count,
            duration_seconds=duration_seconds,
            breakdown=breakdown,
            passed=passed,
            finished_at=finished_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_for_user(self, user_id: int, limit: int = 5) -> list[MockSession]:
        stmt = (
            select(MockSession)
            .where(MockSession.user_id == user_id)
            .order_by(MockSession.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())


__all__ = ["MockSessionRepository"]

from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import Attempt, Question


class AttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_mistake_question_ids(
        self,
        user_id: int,
        limit: int,
        topics: list[str] | None = None,
    ) -> list[int]:
        last_attempt = (
            select(
                Attempt.question_id.label("qid"),
                func.max(Attempt.answered_at).label("latest"),
            )
            .where(Attempt.user_id == user_id)
            .group_by(Attempt.question_id)
            .subquery()
        )
        stmt = (
            select(Attempt.question_id)
            .join(
                last_attempt,
                (Attempt.question_id == last_attempt.c.qid)
                & (Attempt.answered_at == last_attempt.c.latest),
            )
            .join(Question, Question.id == Attempt.question_id)
            .where(
                Attempt.user_id == user_id,
                Attempt.is_correct.is_(False),
                Question.is_active.is_(True),
            )
            .order_by(Attempt.answered_at.desc())
            .limit(limit)
        )
        if topics:
            stmt = stmt.where(Question.topic.in_(topics))
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def bulk_insert(
        self,
        records: Sequence[dict[str, object]],
    ) -> None:
        if not records:
            return
        normalized: list[dict[str, object]] = []
        for record in records:
            answered_at = record.get("answered_at") or datetime.now(UTC)
            session_date = record.get("session_date") or date.today()
            normalized.append(
                {
                    "user_id": record["user_id"],
                    "question_id": record["question_id"],
                    "is_correct": record["is_correct"],
                    "quality": record.get("quality", 0),
                    "response_time_ms": record.get("response_time_ms"),
                    "answered_at": answered_at,
                    "session_date": session_date,
                }
            )
        await self.session.execute(Attempt.__table__.insert(), normalized)

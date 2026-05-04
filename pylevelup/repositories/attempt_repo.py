from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import Attempt


class AttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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

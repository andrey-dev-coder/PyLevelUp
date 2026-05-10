from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import AIUsage


class AIUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_today(self, user_id: int) -> int:
        today = datetime.now(UTC).date()
        stmt = (
            select(func.count(AIUsage.id))
            .where(AIUsage.user_id == user_id)
            .where(AIUsage.usage_date == today)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def record(
        self,
        user_id: int,
        kind: str,
        provider: str,
        model: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> AIUsage:
        usage = AIUsage(
            user_id=user_id,
            usage_date=datetime.now(UTC).date(),
            kind=kind,
            provider=provider,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        self.session.add(usage)
        await self.session.flush()
        return usage

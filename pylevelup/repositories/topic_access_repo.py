from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import UserTopicAccess


class TopicAccessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_topics(self, user_id: int) -> list[str]:
        stmt = select(UserTopicAccess.topic_key).where(UserTopicAccess.user_id == user_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def grant(self, user_id: int, topic_key: str) -> None:
        stmt = pg_insert(UserTopicAccess).values(user_id=user_id, topic_key=topic_key)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=[UserTopicAccess.user_id, UserTopicAccess.topic_key]
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def revoke(self, user_id: int, topic_key: str) -> None:
        stmt = delete(UserTopicAccess).where(
            UserTopicAccess.user_id == user_id,
            UserTopicAccess.topic_key == topic_key,
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def clear(self, user_id: int) -> None:
        stmt = delete(UserTopicAccess).where(UserTopicAccess.user_id == user_id)
        await self.session.execute(stmt)
        await self.session.flush()

    async def replace(self, user_id: int, topic_keys: list[str]) -> None:
        await self.clear(user_id)
        for key in topic_keys:
            await self.grant(user_id, key)

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import Bookmark, Question


class BookmarkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_bookmarked(self, user_id: int, question_id: int) -> bool:
        stmt = select(Bookmark.id).where(
            Bookmark.user_id == user_id,
            Bookmark.question_id == question_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def add(self, user_id: int, question_id: int) -> bool:
        stmt = (
            pg_insert(Bookmark)
            .values(user_id=user_id, question_id=question_id)
            .on_conflict_do_nothing(index_elements=[Bookmark.user_id, Bookmark.question_id])
            .returning(Bookmark.id)
        )
        result = (await self.session.execute(stmt)).scalar_one_or_none()
        await self.session.flush()
        return result is not None

    async def remove(self, user_id: int, question_id: int) -> bool:
        stmt = (
            delete(Bookmark)
            .where(Bookmark.user_id == user_id, Bookmark.question_id == question_id)
            .returning(Bookmark.id)
        )
        removed = (await self.session.execute(stmt)).scalar_one_or_none()
        await self.session.flush()
        return removed is not None

    async def toggle(self, user_id: int, question_id: int) -> bool:
        existing = await self.is_bookmarked(user_id, question_id)
        if existing:
            await self.remove(user_id, question_id)
            return False
        await self.add(user_id, question_id)
        return True

    async def count(self, user_id: int) -> int:
        stmt = select(func.count(Bookmark.id)).where(Bookmark.user_id == user_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def list_questions(
        self, user_id: int, limit: int = 10, offset: int = 0
    ) -> list[Question]:
        stmt = (
            select(Question)
            .join(Bookmark, Bookmark.question_id == Question.id)
            .where(Bookmark.user_id == user_id, Question.is_active.is_(True))
            .order_by(Bookmark.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

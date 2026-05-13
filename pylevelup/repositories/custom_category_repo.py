from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import CustomCategory


class CustomCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[CustomCategory]:
        stmt = select(CustomCategory).order_by(CustomCategory.created_at.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, key: str) -> CustomCategory | None:
        return await self.session.get(CustomCategory, key)

    async def upsert(
        self,
        key: str,
        title: str,
        short: str | None,
        created_by_user_id: int | None,
    ) -> CustomCategory:
        stmt = pg_insert(CustomCategory).values(
            key=key,
            title=title,
            short=short,
            created_by_user_id=created_by_user_id,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[CustomCategory.key],
            set_={
                "title": stmt.excluded.title,
                "short": stmt.excluded.short,
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()
        category = await self.session.get(CustomCategory, key)
        if category is None:
            raise RuntimeError("custom_category_upsert_failed")
        return category

    async def delete(self, key: str) -> bool:
        category = await self.session.get(CustomCategory, key)
        if category is None:
            return False
        await self.session.delete(category)
        await self.session.flush()
        return True

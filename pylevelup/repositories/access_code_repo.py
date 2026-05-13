from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import AccessCode


class AccessCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[AccessCode]:
        stmt = select(AccessCode).order_by(AccessCode.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, code: str) -> AccessCode | None:
        return await self.session.get(AccessCode, code)

    async def upsert(self, code: str, label: str, allowed_topics: list[str]) -> AccessCode:
        stmt = pg_insert(AccessCode).values(
            code=code,
            label=label,
            allowed_topics=allowed_topics,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[AccessCode.code],
            set_={
                "label": label,
                "allowed_topics": allowed_topics,
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return await self.session.get(AccessCode, code)

    async def delete(self, code: str) -> None:
        obj = await self.session.get(AccessCode, code)
        if obj is not None:
            await self.session.delete(obj)
            await self.session.flush()

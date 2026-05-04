from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import BotSetting

ACCESS_CODE_KEY = "access_code"


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> str | None:
        stmt = select(BotSetting).where(BotSetting.key == key)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return row.value if row else None

    async def set(self, key: str, value: str) -> None:
        existing = await self.session.get(BotSetting, key)
        if existing is None:
            self.session.add(BotSetting(key=key, value=value))
        else:
            existing.value = value
        await self.session.flush()

    async def get_or_create(self, key: str, default: str) -> str:
        current = await self.get(key)
        if current is not None:
            return current
        await self.set(key, default)
        return default

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def list_active_for_reminders(self) -> list[User]:
        stmt = select(User).where(User.is_active.is_(True), User.reminders_enabled.is_(True))
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_all_active(self) -> list[User]:
        stmt = select(User).where(User.is_active.is_(True))
        return list((await self.session.execute(stmt)).scalars().all())

    async def upsert_from_telegram(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        language_code: str | None,
    ) -> User:
        stmt = pg_insert(User).values(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            language_code=language_code,
            is_active=True,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[User.telegram_id],
            set_={
                "username": stmt.excluded.username,
                "first_name": stmt.excluded.first_name,
                "language_code": stmt.excluded.language_code,
                "is_active": True,
            },
        ).returning(User.id)
        result = await self.session.execute(stmt)
        user_id = result.scalar_one()
        await self.session.flush()
        user = await self.session.get(User, user_id)
        if user is None:
            raise RuntimeError("user_upsert_failed")
        return user

    async def register_visit(self, user_id: int, today: date) -> User | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        user.total_starts = (user.total_starts or 0) + 1
        if user.last_active_date == today:
            await self.session.flush()
            return user
        if user.last_active_date == today - timedelta(days=1):
            user.current_streak = (user.current_streak or 0) + 1
        else:
            user.current_streak = 1
        if user.current_streak > (user.max_streak or 0):
            user.max_streak = user.current_streak
        user.last_active_date = today
        await self.session.flush()
        return user

    async def update_streak_after_session(self, user_id: int, session_date: date) -> None:
        user = await self.get_by_id(user_id)
        if user is None:
            return
        if user.last_active_date == session_date:
            return
        if user.last_active_date == session_date - timedelta(days=1):
            user.current_streak += 1
        else:
            user.current_streak = 1
        if user.current_streak > user.max_streak:
            user.max_streak = user.current_streak
        user.last_active_date = session_date
        await self.session.flush()

    async def increment_totals(self, user_id: int, correct_delta: int, answered_delta: int) -> None:
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                total_correct=User.total_correct + correct_delta,
                total_answered=User.total_answered + answered_delta,
            )
        )
        await self.session.execute(stmt)

    async def set_ranking(self, user_id: int, score: float, position: int) -> None:
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(ranking_score=score, last_ranking_position=position)
        )
        await self.session.execute(stmt)

    async def set_reminders_enabled(self, user_id: int, enabled: bool) -> None:
        stmt = update(User).where(User.id == user_id).values(reminders_enabled=enabled)
        await self.session.execute(stmt)

    async def mark_authorized(self, telegram_id: int) -> None:
        stmt = (
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(is_authorized=True, is_banned=False, authorized_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)

    async def set_banned(self, telegram_id: int, banned: bool) -> User | None:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        user.is_banned = banned
        user.banned_at = datetime.now(UTC) if banned else None
        if banned:
            user.is_authorized = False
        await self.session.flush()
        return user

    async def find_by_username(self, username: str) -> User | None:
        normalized = username.lstrip("@")
        stmt = select(User).where(func.lower(User.username) == normalized.lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_admin(self, limit: int = 100) -> list[User]:
        stmt = select(User).order_by(User.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.config import Settings
from pylevelup.db.models import User
from pylevelup.repositories import (
    ACCESS_CODE_KEY,
    SettingsRepository,
    UserRepository,
)


class AccessControlMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)
        if event.from_user is None:
            return await handler(event, data)

        settings: Settings = data["settings"]
        session_factory: async_sessionmaker = data["session_factory"]
        telegram_id = event.from_user.id

        if telegram_id == settings.owner_telegram_id:
            user = await self._ensure_owner_user(session_factory, event, settings)
            data["current_user"] = user
            return await handler(event, data)

        async with session_factory() as db:
            users_repo = UserRepository(db)
            settings_repo = SettingsRepository(db)
            user = await users_repo.upsert_from_telegram(
                telegram_id=telegram_id,
                username=event.from_user.username,
                first_name=event.from_user.first_name,
                language_code=event.from_user.language_code,
            )
            await db.commit()
            await db.refresh(user)

            if user.is_banned:
                await self._reject_banned(event)
                return None

            if user.is_authorized:
                data["current_user"] = user
                return await handler(event, data)

            access_code = await settings_repo.get_or_create(
                ACCESS_CODE_KEY, settings.default_access_code
            )
            await db.commit()

            authorized = await self._maybe_authorize(
                event, db, users_repo, telegram_id, access_code
            )
            if authorized:
                await db.commit()
                await self._welcome_after_unlock(event)
                return None

        await self._prompt_for_code(event)
        return None

    async def _ensure_owner_user(
        self,
        session_factory: async_sessionmaker,
        event: Message | CallbackQuery,
        settings: Settings,
    ) -> User:
        async with session_factory() as db:
            users_repo = UserRepository(db)
            user = await users_repo.upsert_from_telegram(
                telegram_id=event.from_user.id,
                username=event.from_user.username,
                first_name=event.from_user.first_name,
                language_code=event.from_user.language_code,
            )
            settings_repo = SettingsRepository(db)
            await settings_repo.get_or_create(
                ACCESS_CODE_KEY, settings.default_access_code
            )
            if not user.is_authorized:
                await users_repo.mark_authorized(event.from_user.id)
                await db.commit()
                user = await users_repo.get_by_telegram_id(event.from_user.id)
            else:
                await db.commit()
            return user

    async def _maybe_authorize(
        self,
        event: Message | CallbackQuery,
        db,
        users_repo: UserRepository,
        telegram_id: int,
        access_code: str,
    ) -> bool:
        if not isinstance(event, Message) or event.text is None:
            return False
        candidate = event.text.strip()
        if candidate.startswith("/"):
            return False
        if candidate != access_code:
            return False
        await users_repo.mark_authorized(telegram_id)
        return True

    async def _reject_banned(self, event: Message | CallbackQuery) -> None:
        text = "Доступ к боту закрыт. Если считаешь это ошибкой, напиши @m203ac."
        if isinstance(event, Message):
            await event.answer(text)
        else:
            await event.answer("Доступ закрыт", show_alert=True)

    async def _prompt_for_code(self, event: Message | CallbackQuery) -> None:
        text = (
            "Этот бот закрытый. Чтобы войти, отправь кодовое слово сообщением.\n"
            "Если у тебя его нет - попроси у @m203ac."
        )
        if isinstance(event, Message):
            await event.answer(text)
        else:
            await event.answer("Сначала введи кодовое слово сообщением", show_alert=True)

    async def _welcome_after_unlock(self, event: Message | CallbackQuery) -> None:
        text = (
            "Кодовое слово принято, доступ открыт.\n"
            "Нажми /start, чтобы открыть главное меню."
        )
        if isinstance(event, Message):
            await event.answer(text)
        else:
            await event.answer("Доступ открыт. Нажми /start", show_alert=True)

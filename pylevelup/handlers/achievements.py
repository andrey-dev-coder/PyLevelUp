from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.repositories import AchievementRepository, UserRepository
from pylevelup.services.achievements import ACHIEVEMENTS

router = Router(name="pylevelup_achievements")


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="В профиль", callback_data="stats:show")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:main")],
        ]
    )


async def _resolve_user_id(session_factory: async_sessionmaker, telegram_id: int) -> int | None:
    async with session_factory() as db:
        user = await UserRepository(db).get_by_telegram_id(telegram_id)
    return user.id if user else None


async def _show(target: Message, session_factory: async_sessionmaker, telegram_id: int) -> None:
    user_id = await _resolve_user_id(session_factory, telegram_id)
    if user_id is None:
        await target.answer("Сначала /start.")
        return
    async with session_factory() as db:
        earned = await AchievementRepository(db).get_user_codes(user_id)
    total = len(ACHIEVEMENTS)
    earned_count = len([a for a in ACHIEVEMENTS if a.code in earned])
    parts: list[str] = [
        f"<b>Ачивки</b>: {earned_count}/{total}",
        "",
    ]
    for item in sorted(ACHIEVEMENTS, key=lambda x: x.sort_order):
        is_earned = item.code in earned
        prefix = item.icon if is_earned else "🔒"
        title = f"<b>{escape(item.title)}</b>" if is_earned else escape(item.title)
        line = f"{prefix} {title} - {escape(item.description)}"
        parts.append(line)
    await target.answer("\n".join(parts), reply_markup=_back_keyboard())


@router.message(Command("achievements"))
async def handle_command(
    message: Message,
    session_factory: async_sessionmaker,
) -> None:
    if message.from_user is None:
        return
    await _show(message, session_factory, message.from_user.id)


@router.callback_query(F.data == "ach:show")
async def handle_callback(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.message is None or call.from_user is None:
        await call.answer()
        return
    await call.answer()
    await _show(call.message, session_factory, call.from_user.id)


__all__ = ["router"]

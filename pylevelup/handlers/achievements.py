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
from pylevelup.utils.edit import safe_edit_text

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


async def _build_text(session_factory: async_sessionmaker, telegram_id: int) -> str | None:
    user_id = await _resolve_user_id(session_factory, telegram_id)
    if user_id is None:
        return None
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
    return "\n".join(parts)


@router.message(Command("achievements"))
async def handle_command(
    message: Message,
    session_factory: async_sessionmaker,
) -> None:
    if message.from_user is None:
        return
    text = await _build_text(session_factory, message.from_user.id)
    if text is None:
        await message.answer("Сначала /start.")
        return
    await message.answer(text, reply_markup=_back_keyboard())


@router.callback_query(F.data == "ach:show")
async def handle_callback(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.message is None or call.from_user is None:
        await call.answer()
        return
    await call.answer()
    text = await _build_text(session_factory, call.from_user.id)
    if text is None:
        await call.message.answer("Сначала /start.")
        return
    await safe_edit_text(call.message, text, reply_markup=_back_keyboard())


__all__ = ["router"]

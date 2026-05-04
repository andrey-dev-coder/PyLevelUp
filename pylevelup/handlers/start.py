from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.keyboards import build_main_menu
from pylevelup.repositories import UserRepository

router = Router(name="pylevelup_start")


@router.message(CommandStart())
async def handle_start(message: Message, session_factory: async_sessionmaker) -> None:
    user = message.from_user
    if user is None:
        return
    async with session_factory() as db:
        repo = UserRepository(db)
        await repo.upsert_from_telegram(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            language_code=user.language_code,
        )
        await db.commit()

    text = (
        "<b>Привет, {name}!</b>\n\n"
        "Я <b>PyLevelUp</b>: бот для ежедневной подготовки к техническим собеседованиям по Python.\n\n"
        "Каждый день ты можешь решать до <b>50 вопросов</b>. Я использую алгоритм интервального "
        "повторения, чтобы возвращать тебе те темы, которые проседают, и не перегружать "
        "повторением того, что ты уже знаешь.\n\n"
        "Команды:\n"
        "/test - запустить ежедневную сессию\n"
        "/stats - моя статистика и место в рейтинге\n"
        "/info - о проекте"
    ).format(name=user.first_name or "коллега")

    await message.answer(text, reply_markup=build_main_menu())

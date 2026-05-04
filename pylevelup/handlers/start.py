from datetime import UTC, datetime

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
        db_user = await repo.upsert_from_telegram(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            language_code=user.language_code,
        )
        await repo.register_visit(db_user.id, datetime.now(UTC).date())
        await db.commit()

    text = (
        "<b>Привет, {name}!</b>\n\n"
        "Я <b>PyLevelUp</b>: бот для подготовки к техническим собеседованиям по Python и бэкенду.\n\n"
        "В банке вопросы по 8 направлениям: Python, алгоритмы, async/concurrency, SQL, HTTP/REST, "
        "Django ORM, кэширование, системный дизайн. Я использую алгоритм интервального повторения - "
        "буду возвращать темы, которые проседают, и реже показывать то, что ты уже знаешь.\n\n"
        "Команды:\n"
        "/test - выбрать категорию и запустить тест\n"
        "/algorithms - сразу к алгоритмам\n"
        "/stats - моя статистика и место в рейтинге\n"
        "/info - о проекте"
    ).format(name=user.first_name or "коллега")

    await message.answer(text, reply_markup=build_main_menu())

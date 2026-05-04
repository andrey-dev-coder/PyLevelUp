from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.repositories import UserRepository
from pylevelup.services import StatsService

router = Router(name="pylevelup_stats")


def _format_stats(stats) -> str:
    if stats is None or stats.total_answered == 0:
        return (
            "<b>Статистика пуста.</b>\n\n"
            "Запусти первую сессию командой /test, и я начну считать твой стрик, "
            "точность ответов и место в глобальном рейтинге."
        )
    return (
        "<b>Твоя статистика</b>\n\n"
        f"Текущий стрик: <b>{stats.current_streak}</b> дн.\n"
        f"Максимальный стрик: <b>{stats.max_streak}</b> дн.\n"
        f"Правильных ответов: <b>{stats.total_correct}</b> из <b>{stats.total_answered}</b>\n"
        f"Точность: <b>{stats.accuracy_percent}%</b>\n"
        f"Рейтинг: <b>{stats.ranking_position}</b> из <b>{stats.total_users}</b>\n"
        f"Очки: <b>{stats.ranking_score}</b>"
    )


async def _send_stats(target: Message, telegram_id: int, session_factory: async_sessionmaker) -> None:
    async with session_factory() as db:
        user = await UserRepository(db).get_by_telegram_id(telegram_id)
        if user is None:
            await target.answer(_format_stats(None))
            return
        stats = await StatsService(db).get_user_stats(user.id)
    await target.answer(_format_stats(stats))


@router.message(Command("stats"))
async def handle_stats(message: Message, session_factory: async_sessionmaker) -> None:
    if message.from_user is None:
        return
    await _send_stats(message, message.from_user.id, session_factory)


@router.callback_query(F.data == "stats:show")
async def handle_stats_callback(callback: CallbackQuery, session_factory: async_sessionmaker) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    await _send_stats(callback.message, callback.from_user.id, session_factory)
    await callback.answer()

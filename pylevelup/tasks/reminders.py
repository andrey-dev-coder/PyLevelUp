import asyncio

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramNotFound

from pylevelup.celery_app import celery_app
from pylevelup.config import get_settings
from pylevelup.db.session import create_async_engine_instance, create_async_sessionmaker
from pylevelup.logger import configure_logging, get_logger
from pylevelup.repositories import UserRepository

logger = get_logger(__name__)

REMINDER_TEXT = (
    "Доброе утро! Время прокачать Python: запусти /test и закрой ежедневную "
    "норму вопросов до собеса."
)


async def _broadcast() -> int:
    settings = get_settings()
    engine = create_async_engine_instance(settings.database_url)
    sessionmaker = create_async_sessionmaker(engine)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    sent = 0
    try:
        async with sessionmaker() as db:
            users = await UserRepository(db).list_active_for_reminders()
        for user in users:
            try:
                await bot.send_message(chat_id=user.telegram_id, text=REMINDER_TEXT)
                sent += 1
            except TelegramForbiddenError:
                async with sessionmaker() as db:
                    await UserRepository(db).set_reminders_enabled(user.id, False)
                    await db.commit()
            except TelegramNotFound:
                continue
            except Exception as exc:
                logger.warning("reminder_failed", user_id=user.id, error=str(exc))
    finally:
        await bot.session.close()
        await engine.dispose()
    return sent


@celery_app.task(name="pylevelup.tasks.reminders.send_daily_reminders")
def send_daily_reminders() -> int:
    configure_logging()
    return asyncio.run(_broadcast())

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat
from redis.asyncio import Redis

from pylevelup.config import Settings, get_settings
from pylevelup.db.session import create_async_engine_instance, create_async_sessionmaker
from pylevelup.handlers import build_root_router
from pylevelup.logger import configure_logging, get_logger
from pylevelup.middlewares import AccessControlMiddleware
from pylevelup.services.session_cache import RedisSessionCache
from pylevelup.services.spaced_repetition import SpacedRepetitionEngine
from pylevelup.services.study_service import StudyService
from pylevelup.services.test_session_service import TestSessionService

logger = get_logger(__name__)


BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="test", description="Начать тест по выбранной категории"),
    BotCommand(command="daily", description="Челлендж дня"),
    BotCommand(command="mock", description="Mock-собеседование"),
    BotCommand(command="algorithms", description="Тренировка алгоритмов"),
    BotCommand(command="mistakes", description="Работа над ошибками"),
    BotCommand(command="bookmarks", description="Закладки"),
    BotCommand(command="cheatsheet", description="Шпаргалки по темам"),
    BotCommand(command="search", description="Поиск по вопросам"),
    BotCommand(command="achievements", description="Мои ачивки"),
    BotCommand(command="stats", description="Мой профиль и статистика"),
    BotCommand(command="info", description="О проекте и контакты"),
)

OWNER_COMMANDS: tuple[BotCommand, ...] = BOT_COMMANDS + (
    BotCommand(command="broadcast", description="Рассылка всем пользователям"),
    BotCommand(command="broadcast_test", description="Превью рассылки только себе"),
    BotCommand(command="setcode", description="Сменить кодовое слово"),
    BotCommand(command="getcode", description="Показать текущее кодовое слово"),
    BotCommand(command="ban", description="Забанить пользователя"),
    BotCommand(command="unban", description="Разбанить пользователя"),
    BotCommand(command="users", description="Список пользователей"),
)


async def _on_startup(bot: Bot, settings_obj: Settings) -> None:
    me = await bot.get_me()
    await bot.set_my_commands(
        commands=list(BOT_COMMANDS),
        scope=BotCommandScopeAllPrivateChats(),
    )
    try:
        await bot.set_my_commands(
            commands=list(OWNER_COMMANDS),
            scope=BotCommandScopeChat(chat_id=settings_obj.owner_telegram_id),
        )
    except Exception as exc:
        logger.warning("owner_commands_set_failed", error=str(exc))
    logger.info("bot_started", username=me.username, id=me.id)


async def _on_shutdown(bot: Bot) -> None:
    logger.info("bot_shutdown")


async def _run(settings: Settings) -> None:
    engine = create_async_engine_instance(settings.database_url)
    sessionmaker = create_async_sessionmaker(engine)

    fsm_redis = Redis.from_url(settings.redis_fsm_url)
    cache_redis = Redis.from_url(settings.redis_cache_url)

    storage = RedisStorage(redis=fsm_redis)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    session_cache = RedisSessionCache(cache_redis, ttl_seconds=settings.session_timeout_seconds)
    sr_engine = SpacedRepetitionEngine()
    session_service = TestSessionService(
        session_factory=sessionmaker,
        cache=session_cache,
        engine=sr_engine,
        settings=settings,
    )
    study_service = StudyService(
        session_factory=sessionmaker,
        redis=cache_redis,
        ttl_seconds=settings.session_timeout_seconds,
    )

    dp["session_factory"] = sessionmaker
    dp["session_service"] = session_service
    dp["session_cache"] = session_cache
    dp["study_service"] = study_service
    dp["settings"] = settings

    access_mw = AccessControlMiddleware()
    dp.message.outer_middleware(access_mw)
    dp.callback_query.outer_middleware(access_mw)

    dp.include_router(build_root_router())

    async def _startup_wrapper(bot: Bot) -> None:
        await _on_startup(bot, settings)

    dp.startup.register(_startup_wrapper)
    dp.shutdown.register(_on_shutdown)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await fsm_redis.aclose()
        await cache_redis.aclose()
        await engine.dispose()


def main() -> None:
    configure_logging()
    settings = get_settings()
    asyncio.run(_run(settings))


if __name__ == "__main__":
    main()

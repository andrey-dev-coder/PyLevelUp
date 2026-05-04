import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from pylevelup.config import Settings, get_settings
from pylevelup.db.session import create_async_engine_instance, create_async_sessionmaker
from pylevelup.handlers import build_root_router
from pylevelup.logger import configure_logging, get_logger
from pylevelup.services.session_cache import RedisSessionCache
from pylevelup.services.spaced_repetition import SpacedRepetitionEngine
from pylevelup.services.test_session_service import TestSessionService

logger = get_logger(__name__)


async def _on_startup(bot: Bot) -> None:
    me = await bot.get_me()
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

    dp["session_factory"] = sessionmaker
    dp["session_service"] = session_service
    dp["session_cache"] = session_cache
    dp["settings"] = settings

    dp.include_router(build_root_router())
    dp.startup.register(_on_startup)
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

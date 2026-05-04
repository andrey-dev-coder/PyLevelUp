import asyncio

from pylevelup.celery_app import celery_app
from pylevelup.config import get_settings
from pylevelup.db.session import create_async_engine_instance, create_async_sessionmaker
from pylevelup.logger import configure_logging, get_logger
from pylevelup.services.ranking_service import RankingService

logger = get_logger(__name__)


async def _refresh() -> int:
    settings = get_settings()
    engine = create_async_engine_instance(settings.database_url)
    sessionmaker = create_async_sessionmaker(engine)
    try:
        async with sessionmaker() as db:
            updated = await RankingService(db).recompute_global_ranking()
            await db.commit()
        return updated
    finally:
        await engine.dispose()


@celery_app.task(name="pylevelup.tasks.ranking.refresh_ranking")
def refresh_ranking() -> int:
    configure_logging()
    updated = asyncio.run(_refresh())
    logger.info("ranking_refreshed", users=updated)
    return updated

import asyncio

from sqlalchemy.dialects.postgresql import insert as pg_insert

from pylevelup.config import get_settings
from pylevelup.db.models import Achievement
from pylevelup.db.session import create_async_engine_instance, create_async_sessionmaker
from pylevelup.logger import configure_logging, get_logger
from pylevelup.services.achievements import ACHIEVEMENTS

logger = get_logger(__name__)


async def _seed() -> int:
    settings = get_settings()
    engine = create_async_engine_instance(settings.database_url)
    sessionmaker = create_async_sessionmaker(engine)
    inserted = 0
    try:
        async with sessionmaker() as db:
            for index, item in enumerate(ACHIEVEMENTS):
                stmt = pg_insert(Achievement).values(
                    code=item.code,
                    title=item.title,
                    description=item.description,
                    icon=item.icon,
                    sort_order=item.sort_order,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[Achievement.code],
                    set_={
                        "title": stmt.excluded.title,
                        "description": stmt.excluded.description,
                        "icon": stmt.excluded.icon,
                        "sort_order": stmt.excluded.sort_order,
                    },
                )
                await db.execute(stmt)
                inserted += 1
                _ = index
            await db.commit()
    finally:
        await engine.dispose()
    return inserted


def main() -> None:
    configure_logging()
    count = asyncio.run(_seed())
    logger.info("seed_achievements_done", count=count)


if __name__ == "__main__":
    main()

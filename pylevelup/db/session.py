from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from pylevelup.config import get_settings


def create_async_engine_instance(url: str) -> AsyncEngine:
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        future=True,
    )


def create_async_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine_instance(settings.database_url)


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return create_async_sessionmaker(get_engine())

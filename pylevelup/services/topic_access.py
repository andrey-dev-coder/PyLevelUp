from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.repositories import TopicAccessRepository, UserRepository


async def get_allowed_topics(
    session_factory: async_sessionmaker,
    telegram_id: int,
) -> set[str] | None:
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        repo = TopicAccessRepository(db)
        topics = await repo.list_topics(user.id)
    if not topics:
        return None
    return set(topics)


def filter_topics(
    candidates: list[str],
    allowed: set[str] | None,
) -> list[str]:
    if allowed is None:
        return candidates
    return [t for t in candidates if t in allowed]

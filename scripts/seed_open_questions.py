import asyncio
import json
import sys
from pathlib import Path

from pylevelup.config import get_settings
from pylevelup.db.session import create_async_engine_instance, create_async_sessionmaker
from pylevelup.logger import configure_logging, get_logger
from pylevelup.repositories import OpenQuestionRepository

logger = get_logger(__name__)


def _read(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


async def _seed(path: Path) -> int:
    raw = _read(path)
    settings = get_settings()
    engine = create_async_engine_instance(settings.database_url)
    sessionmaker = create_async_sessionmaker(engine)
    inserted = 0
    try:
        async with sessionmaker() as db:
            repo = OpenQuestionRepository(db)
            for item in raw:
                await repo.upsert(
                    external_key=item["external_key"],
                    topic=item["topic"],
                    difficulty=int(item.get("difficulty", 2)),
                    text=item["text"],
                    ideal_answer=item["ideal_answer"],
                    checklist=item.get("checklist") or None,
                )
                inserted += 1
            await db.commit()
    finally:
        await engine.dispose()
    return inserted


def main() -> None:
    configure_logging()
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = Path(__file__).resolve().parent.parent / "data" / "open_questions.json"
    if not path.exists():
        logger.error("seed_open_file_missing", path=str(path))
        raise SystemExit(2)
    count = asyncio.run(_seed(path))
    logger.info("seed_open_done", count=count, path=str(path))


if __name__ == "__main__":
    main()

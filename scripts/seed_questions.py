import asyncio
import json
import sys
from pathlib import Path

from pylevelup.config import get_settings
from pylevelup.db.session import create_async_engine_instance, create_async_sessionmaker
from pylevelup.logger import configure_logging, get_logger
from pylevelup.repositories import QuestionRepository

logger = get_logger(__name__)


def _read_questions(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


async def _seed(path: Path) -> int:
    raw = _read_questions(path)
    settings = get_settings()
    engine = create_async_engine_instance(settings.database_url)
    sessionmaker = create_async_sessionmaker(engine)

    inserted = 0
    try:
        async with sessionmaker() as db:
            repo = QuestionRepository(db)
            for item in raw:
                await repo.upsert_external(
                    external_key=item["external_key"],
                    topic=item["topic"],
                    difficulty=int(item.get("difficulty", 1)),
                    text=item["text"],
                    options=list(item["options"]),
                    correct_index=int(item["correct_index"]),
                    explanation=item.get("explanation"),
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
        path = Path(__file__).resolve().parent.parent / "data" / "questions.json"
    if not path.exists():
        logger.error("seed_file_missing", path=str(path))
        raise SystemExit(2)
    count = asyncio.run(_seed(path))
    logger.info("seed_done", count=count, path=str(path))


if __name__ == "__main__":
    main()

import asyncio
from datetime import UTC, datetime, timedelta
from html import escape

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramNotFound
from sqlalchemy import case, func, select

from pylevelup.categories import display_name
from pylevelup.celery_app import celery_app
from pylevelup.config import get_settings
from pylevelup.db.models import Attempt, Question, User
from pylevelup.db.session import create_async_engine_instance, create_async_sessionmaker
from pylevelup.logger import configure_logging, get_logger
from pylevelup.repositories import UserRepository

logger = get_logger(__name__)


async def _user_week_summary(session, user_id: int, since: datetime) -> dict | None:
    total_stmt = select(
        func.count(Attempt.id).label("total"),
        func.sum(case((Attempt.is_correct.is_(True), 1), else_=0)).label("correct"),
    ).where(Attempt.user_id == user_id, Attempt.created_at >= since)
    total_row = (await session.execute(total_stmt)).one()
    total = int(total_row.total or 0)
    correct = int(total_row.correct or 0)
    if total == 0:
        return None

    topic_stmt = (
        select(
            Question.topic.label("topic"),
            func.count(Attempt.id).label("total"),
            func.sum(case((Attempt.is_correct.is_(True), 1), else_=0)).label("correct"),
        )
        .join(Question, Question.id == Attempt.question_id)
        .where(Attempt.user_id == user_id, Attempt.created_at >= since)
        .group_by(Question.topic)
    )
    topic_rows = (await session.execute(topic_stmt)).all()
    topics: list[tuple[str, int, int, float]] = []
    for r in topic_rows:
        t_total = int(r.total or 0)
        t_correct = int(r.correct or 0)
        if t_total < 3:
            continue
        accuracy = t_correct / t_total * 100.0
        topics.append((str(r.topic), t_total, t_correct, accuracy))
    topics.sort(key=lambda x: x[3], reverse=True)
    best = topics[0] if topics else None
    weakest = topics[-1] if topics and topics[-1] != best else None

    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total * 100.0 if total else 0.0,
        "best": best,
        "weakest": weakest,
    }


def _format_summary(summary: dict, first_name: str | None) -> str:
    name = escape(first_name) if first_name else "коллега"
    parts: list[str] = [
        f"<b>Итоги недели для {name}</b>",
        "",
        f"Вопросов отвечено: <b>{summary['total']}</b>",
        f"Правильных: <b>{summary['correct']}</b> ({summary['accuracy']:.0f}%)",
    ]
    if summary["best"]:
        topic, _t, _c, acc = summary["best"]
        parts.append(f"Сильнее всего: <b>{escape(display_name(topic))}</b> ({acc:.0f}%)")
    if summary["weakest"]:
        topic, _t, _c, acc = summary["weakest"]
        parts.append(f"Слабее всего: <b>{escape(display_name(topic))}</b> ({acc:.0f}%)")
    parts.append("")
    parts.append("Так держать! Жми /test и продолжай.")
    return "\n".join(parts)


async def _send_digests() -> int:
    settings = get_settings()
    engine = create_async_engine_instance(settings.database_url)
    sessionmaker = create_async_sessionmaker(engine)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    sent = 0
    since = datetime.now(UTC) - timedelta(days=7)
    try:
        async with sessionmaker() as db:
            stmt = select(User).where(
                User.is_active.is_(True),
                User.is_authorized.is_(True),
                User.reminders_enabled.is_(True),
            )
            users = list((await db.execute(stmt)).scalars().all())

        for user in users:
            async with sessionmaker() as db:
                summary = await _user_week_summary(db, user.id, since)
            if summary is None:
                continue
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=_format_summary(summary, user.first_name),
                )
                sent += 1
            except TelegramForbiddenError:
                async with sessionmaker() as db:
                    await UserRepository(db).set_reminders_enabled(user.id, False)
                    await db.commit()
            except TelegramNotFound:
                continue
            except Exception as exc:
                logger.warning("digest_failed", user_id=user.id, error=str(exc))
            await asyncio.sleep(0.05)
    finally:
        await bot.session.close()
        await engine.dispose()
    return sent


@celery_app.task(name="pylevelup.tasks.digest.send_weekly_digest")
def send_weekly_digest() -> int:
    configure_logging()
    return asyncio.run(_send_digests())

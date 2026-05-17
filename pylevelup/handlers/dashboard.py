from datetime import UTC, datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.categories import display_name
from pylevelup.config import Settings
from pylevelup.db.models import (
    Attempt,
    MockSession,
    Question,
    QuestionReport,
    User,
)
from pylevelup.utils.text import clean_text

router = Router(name="pylevelup_dashboard")

TOP_FAILED_LIMIT = 10


def _is_owner(actor_id: int, settings: Settings) -> bool:
    return actor_id == settings.owner_telegram_id


async def _dau(db, since: datetime) -> int:
    stmt = (
        select(func.count(distinct(Attempt.user_id)))
        .where(Attempt.answered_at >= since)
    )
    return int((await db.execute(stmt)).scalar_one())


async def _attempts_count(db, since: datetime) -> tuple[int, int]:
    stmt = select(
        func.count(Attempt.id),
        func.coalesce(func.sum(case((Attempt.is_correct, 1), else_=0)), 0),
    ).where(Attempt.answered_at >= since)
    row = (await db.execute(stmt)).one()
    return int(row[0] or 0), int(row[1] or 0)


async def _total_users(db) -> int:
    return int(
        (await db.execute(select(func.count(User.id)))).scalar_one()
    )


async def _new_users_since(db, since: datetime) -> int:
    stmt = select(func.count(User.id)).where(User.created_at >= since)
    return int((await db.execute(stmt)).scalar_one())


async def _active_mock_sessions(db) -> int:
    stmt = select(func.count(MockSession.id)).where(MockSession.finished_at.is_(None))
    return int((await db.execute(stmt)).scalar_one())


async def _open_reports(db) -> int:
    stmt = select(func.count(QuestionReport.id)).where(QuestionReport.status == "open")
    return int((await db.execute(stmt)).scalar_one())


async def _funnel(db, since: datetime) -> dict[str, int]:
    user_ids_stmt = select(User.id).where(User.created_at >= since)
    user_ids = [int(uid) for uid in (await db.execute(user_ids_stmt)).scalars().all()]
    if not user_ids:
        return {
            "starts": 0,
            "authorized": 0,
            "attempted": 0,
            "five_plus": 0,
            "returned": 0,
            "streak_7": 0,
        }
    starts = len(user_ids)
    authorized_stmt = (
        select(func.count(User.id))
        .where(User.created_at >= since, User.is_authorized.is_(True))
    )
    authorized = int((await db.execute(authorized_stmt)).scalar_one() or 0)
    attempt_counts_stmt = (
        select(Attempt.user_id, func.count(Attempt.id))
        .where(Attempt.user_id.in_(user_ids))
        .group_by(Attempt.user_id)
    )
    attempt_counts = {
        int(row[0]): int(row[1] or 0)
        for row in (await db.execute(attempt_counts_stmt)).all()
    }
    attempted = sum(1 for c in attempt_counts.values() if c >= 1)
    five_plus = sum(1 for c in attempt_counts.values() if c >= 5)
    distinct_days_stmt = (
        select(Attempt.user_id, func.count(distinct(Attempt.session_date)))
        .where(Attempt.user_id.in_(user_ids))
        .group_by(Attempt.user_id)
    )
    distinct_days = {
        int(row[0]): int(row[1] or 0)
        for row in (await db.execute(distinct_days_stmt)).all()
    }
    returned = sum(1 for c in distinct_days.values() if c >= 2)
    streak_stmt = (
        select(func.count(User.id))
        .where(User.created_at >= since, User.max_streak >= 7)
    )
    streak_7 = int((await db.execute(streak_stmt)).scalar_one() or 0)
    return {
        "starts": starts,
        "authorized": authorized,
        "attempted": attempted,
        "five_plus": five_plus,
        "returned": returned,
        "streak_7": streak_7,
    }


def _funnel_line(label: str, value: int, base: int) -> str:
    if base <= 0:
        return f"{label}: <b>{value}</b>"
    pct = value / base * 100
    return f"{label}: <b>{value}</b> ({pct:.0f}%)"


def _format_funnel(rows: dict[str, int], window_label: str) -> str:
    base = rows["starts"]
    lines = [
        f"<b>Воронка (юзеры пришли за {window_label})</b>",
        _funnel_line("• /start", rows["starts"], base),
        _funnel_line("• Авторизованы", rows["authorized"], base),
        _funnel_line("• Ответили на 1+ вопрос", rows["attempted"], base),
        _funnel_line("• Решили 5+ вопросов", rows["five_plus"], base),
        _funnel_line("• Вернулись 2+ дня", rows["returned"], base),
        _funnel_line("• Стрик 7+ дней", rows["streak_7"], base),
    ]
    return "\n".join(lines)


async def _top_failed_questions(db, since: datetime, limit: int) -> list[tuple[Question, int, int]]:
    wrong_expr = func.coalesce(
        func.sum(case((Attempt.is_correct.is_(False), 1), else_=0)), 0
    ).label("wrong")
    total_expr = func.count(Attempt.id).label("total")
    stmt = (
        select(Attempt.question_id, total_expr, wrong_expr)
        .where(Attempt.answered_at >= since)
        .group_by(Attempt.question_id)
        .having(func.count(Attempt.id) >= 5)
        .order_by(wrong_expr.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return []
    question_ids = [r[0] for r in rows]
    q_stmt = select(Question).where(Question.id.in_(question_ids))
    questions_by_id = {q.id: q for q in (await db.execute(q_stmt)).scalars().all()}
    result: list[tuple[Question, int, int]] = []
    for question_id, total, wrong in rows:
        q = questions_by_id.get(question_id)
        if q is None:
            continue
        result.append((q, int(total or 0), int(wrong or 0)))
    return result


def _format_top_failed(rows: list[tuple[Question, int, int]]) -> str:
    if not rows:
        return "  (мало данных, нужно минимум 5 ответов на вопрос)"
    lines: list[str] = []
    for idx, (q, total, wrong) in enumerate(rows, start=1):
        rate = (wrong / total * 100) if total else 0.0
        snippet = clean_text(q.text)
        if len(snippet) > 80:
            snippet = snippet[:80].rstrip() + "..."
        lines.append(
            f"{idx}. #{q.id} [{display_name(q.topic)}] {rate:.0f}% ({wrong}/{total})"
        )
        lines.append(f"   {snippet}")
    return "\n".join(lines)


@router.message(Command("admin"))
async def handle_admin(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None or not _is_owner(message.from_user.id, settings):
        return
    now = datetime.now(UTC)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    async with session_factory() as db:
        total_users = await _total_users(db)
        new_24h = await _new_users_since(db, day_ago)
        new_7d = await _new_users_since(db, week_ago)
        dau = await _dau(db, day_ago)
        wau = await _dau(db, week_ago)
        mau = await _dau(db, month_ago)
        attempts_24h, correct_24h = await _attempts_count(db, day_ago)
        attempts_7d, correct_7d = await _attempts_count(db, week_ago)
        active_mocks = await _active_mock_sessions(db)
        open_reports = await _open_reports(db)
        funnel_7d = await _funnel(db, week_ago)
        funnel_30d = await _funnel(db, month_ago)
        top_failed = await _top_failed_questions(db, month_ago, TOP_FAILED_LIMIT)
    accuracy_24h = (correct_24h / attempts_24h * 100) if attempts_24h else 0.0
    accuracy_7d = (correct_7d / attempts_7d * 100) if attempts_7d else 0.0
    lines = [
        "<b>Owner dashboard</b>",
        f"Время: {now:%Y-%m-%d %H:%M UTC}",
        "",
        "<b>Пользователи</b>",
        f"Всего: <b>{total_users}</b>",
        f"Новых за 24ч / 7д: <b>{new_24h}</b> / <b>{new_7d}</b>",
        f"DAU / WAU / MAU: <b>{dau}</b> / <b>{wau}</b> / <b>{mau}</b>",
        "",
        "<b>Ответы</b>",
        f"За 24ч: <b>{attempts_24h}</b> (точность {accuracy_24h:.1f}%)",
        f"За 7д: <b>{attempts_7d}</b> (точность {accuracy_7d:.1f}%)",
        "",
        "<b>Сессии и жалобы</b>",
        f"Активных mock-сессий: <b>{active_mocks}</b>",
        f"Открытых жалоб: <b>{open_reports}</b>",
        "",
        _format_funnel(funnel_7d, "7 дней"),
        "",
        _format_funnel(funnel_30d, "30 дней"),
        "",
        f"<b>Топ-{TOP_FAILED_LIMIT} самых проваливаемых вопросов (30д)</b>",
        _format_top_failed(top_failed),
    ]
    await message.answer("\n".join(lines))


__all__ = ["router"]

from datetime import UTC, datetime, timedelta
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.categories import CATEGORIES, custom_categories, display_name
from pylevelup.config import Settings
from pylevelup.db.models import (
    Attempt,
    Bookmark,
    DailyChallengeAttempt,
    MockSession,
    Question,
    User,
    UserAchievement,
)
from pylevelup.repositories import (
    TopicAccessRepository,
    UserRepository,
)
from pylevelup.utils.edit import safe_edit_text

router = Router(name="pylevelup_user_admin")


def _is_owner(user_id: int | None, settings: Settings) -> bool:
    return user_id is not None and user_id == settings.owner_telegram_id


async def _resolve(repo: UserRepository, raw: str) -> User | None:
    raw = raw.strip()
    if raw.startswith("@"):
        return await repo.find_by_username(raw)
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        return await repo.get_by_telegram_id(int(raw))
    return await repo.find_by_username(raw)


def _all_known_keys() -> list[str]:
    return [c.key for c in CATEGORIES] + [c.key for c in custom_categories()]


def _user_topics_keyboard(user_id: int, allowed: set[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    is_default = len(allowed) == 0
    for cat in CATEGORIES:
        checked = is_default or cat.key in allowed
        prefix = "☑" if checked else "▫️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix} {cat.short}",
                    callback_data=f"ut:t:{user_id}:{cat.key}",
                )
            ]
        )
    for cat in custom_categories():
        checked = is_default or cat.key in allowed
        prefix = "☑" if checked else "▫️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix} {cat.short} (своя)",
                    callback_data=f"ut:t:{user_id}:{cat.key}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="Все темы (сброс к дефолту)",
                callback_data=f"ut:reset:{user_id}",
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="Закрыть", callback_data="ut:close")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _user_header(user: User, allowed: list[str]) -> str:
    name = escape(user.username or user.first_name or "без имени")
    if user.username:
        name = f"@{escape(user.username)}"
    status_parts: list[str] = []
    if user.is_banned:
        status_parts.append("забанен")
    elif user.is_authorized:
        status_parts.append("авторизован")
    else:
        status_parts.append("не авторизован")
    if not user.is_active:
        status_parts.append("неактивен")
    status = ", ".join(status_parts)
    if not allowed:
        access = "все темы (по умолчанию)"
    else:
        access = f"{len(allowed)} тем"
    return (
        f"<b>Пользователь</b>\n"
        f"ID: <code>{user.telegram_id}</code> | {name}\n"
        f"Статус: {status}\n"
        f"Доступ: {access}\n"
    )


@router.message(Command("user_topics"))
async def handle_user_topics_cmd(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(message.from_user.id if message.from_user else None, settings):
        return
    target = (command.args or "").strip()
    if not target:
        await message.answer(
            "Использование: /user_topics TELEGRAM_ID или /user_topics @username"
        )
        return
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await _resolve(user_repo, target)
        if user is None:
            await message.answer("Пользователь не найден в базе.")
            return
        repo = TopicAccessRepository(db)
        allowed = await repo.list_topics(user.id)
    text = _user_header(user, allowed) + (
        "\nОтметь темы, которые открыть юзеру. "
        "Пустой список = все темы доступны (дефолт)."
    )
    await message.answer(
        text,
        reply_markup=_user_topics_keyboard(user.id, set(allowed)),
    )


@router.callback_query(F.data.startswith("ut:t:"))
async def handle_toggle_user_topic(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    parts = call.data.split(":", 3)
    if len(parts) != 4:
        await call.answer()
        return
    try:
        user_id = int(parts[2])
    except ValueError:
        await call.answer()
        return
    topic_key = parts[3]
    known = set(_all_known_keys())
    if topic_key not in known:
        await call.answer("Неизвестная категория", show_alert=True)
        return
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            await call.answer("Пользователь не найден")
            return
        repo = TopicAccessRepository(db)
        current = await repo.list_topics(user.id)
        if not current:
            new_allowed = [k for k in known if k != topic_key]
            for k in new_allowed:
                await repo.grant(user.id, k)
        elif topic_key in current:
            await repo.revoke(user.id, topic_key)
            new_allowed = [k for k in current if k != topic_key]
        else:
            await repo.grant(user.id, topic_key)
            new_allowed = current + [topic_key]
        if set(new_allowed) == known:
            await repo.clear(user.id)
            new_allowed = []
        await db.commit()
    await call.answer()
    text = _user_header(user, new_allowed) + (
        "\nОтметь темы, которые открыть юзеру."
    )
    await safe_edit_text(
        call.message,
        text,
        reply_markup=_user_topics_keyboard(user.id, set(new_allowed)),
    )


@router.callback_query(F.data.startswith("ut:reset:"))
async def handle_reset_user_topics(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    try:
        user_id = int(call.data.split(":", 2)[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            await call.answer("Пользователь не найден")
            return
        repo = TopicAccessRepository(db)
        await repo.clear(user.id)
        await db.commit()
    await call.answer("Сброшено к дефолту")
    text = _user_header(user, []) + (
        "\nОтметь темы, которые открыть юзеру."
    )
    await safe_edit_text(
        call.message,
        text,
        reply_markup=_user_topics_keyboard(user.id, set()),
    )


@router.callback_query(F.data == "ut:close")
async def handle_close_user_topics(
    call: CallbackQuery,
    settings: Settings,
) -> None:
    if not _is_owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    await call.answer()
    if call.message is not None:
        await safe_edit_text(call.message, "Окно настройки доступа закрыто.")


@router.message(Command("user_stats"))
async def handle_user_stats_cmd(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(message.from_user.id if message.from_user else None, settings):
        return
    target = (command.args or "").strip()
    if not target:
        await message.answer(
            "Использование: /user_stats TELEGRAM_ID или /user_stats @username"
        )
        return
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await _resolve(user_repo, target)
        if user is None:
            await message.answer("Пользователь не найден в базе.")
            return
        report = await _build_user_report(db, user)
    await message.answer(report)


async def _build_user_report(db, user: User) -> str:
    now = datetime.now(UTC)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    total_stmt = select(
        func.count(Attempt.id),
        func.coalesce(func.sum(case((Attempt.is_correct, 1), else_=0)), 0),
        func.coalesce(func.avg(Attempt.response_time_ms), 0),
    ).where(Attempt.user_id == user.id)
    total_row = (await db.execute(total_stmt)).one()
    total_attempts = int(total_row[0] or 0)
    total_correct = int(total_row[1] or 0)
    avg_time_ms = int(total_row[2] or 0)

    week_stmt = select(
        func.count(Attempt.id),
        func.coalesce(func.sum(case((Attempt.is_correct, 1), else_=0)), 0),
    ).where(Attempt.user_id == user.id, Attempt.answered_at >= seven_days_ago)
    week_row = (await db.execute(week_stmt)).one()
    week_attempts = int(week_row[0] or 0)
    week_correct = int(week_row[1] or 0)

    month_stmt = select(
        func.count(Attempt.id),
    ).where(Attempt.user_id == user.id, Attempt.answered_at >= thirty_days_ago)
    month_attempts = int((await db.execute(month_stmt)).scalar_one() or 0)

    active_days_stmt = select(
        func.count(distinct(Attempt.session_date))
    ).where(Attempt.user_id == user.id, Attempt.answered_at >= thirty_days_ago)
    active_days = int((await db.execute(active_days_stmt)).scalar_one() or 0)

    topic_stmt = (
        select(
            Question.topic,
            func.count(Attempt.id).label("cnt"),
            func.coalesce(func.sum(case((Attempt.is_correct, 1), else_=0)), 0).label("ok"),
        )
        .join(Question, Question.id == Attempt.question_id)
        .where(Attempt.user_id == user.id)
        .group_by(Question.topic)
        .order_by(func.count(Attempt.id).desc())
    )
    topic_rows = list((await db.execute(topic_stmt)).all())

    mock_stmt = select(
        func.count(MockSession.id),
        func.coalesce(func.sum(MockSession.correct_count), 0),
        func.coalesce(func.sum(MockSession.total_questions), 0),
    ).where(MockSession.user_id == user.id, MockSession.finished.is_(True))
    mock_row = (await db.execute(mock_stmt)).one()
    mock_finished = int(mock_row[0] or 0)
    mock_correct = int(mock_row[1] or 0)
    mock_total = int(mock_row[2] or 0)

    daily_stmt = select(
        func.count(DailyChallengeAttempt.id),
        func.coalesce(func.sum(case((DailyChallengeAttempt.is_correct, 1), else_=0)), 0),
    ).where(DailyChallengeAttempt.user_id == user.id)
    daily_row = (await db.execute(daily_stmt)).one()
    daily_attempts = int(daily_row[0] or 0)
    daily_correct = int(daily_row[1] or 0)

    bookmarks_count = int(
        (await db.execute(select(func.count(Bookmark.id)).where(Bookmark.user_id == user.id))).scalar_one() or 0
    )
    achievements_count = int(
        (await db.execute(select(func.count(UserAchievement.id)).where(UserAchievement.user_id == user.id))).scalar_one() or 0
    )

    last_attempt_stmt = (
        select(func.max(Attempt.answered_at))
        .where(Attempt.user_id == user.id)
    )
    last_attempt_at = (await db.execute(last_attempt_stmt)).scalar_one_or_none()

    repo = TopicAccessRepository(db)
    allowed_topics = await repo.list_topics(user.id)

    name = (
        f"@{escape(user.username)}"
        if user.username
        else escape(user.first_name or "без имени")
    )

    def pct(num: int, denom: int) -> str:
        if denom <= 0:
            return "0%"
        return f"{round(num / denom * 100)}%"

    lines = [
        "<b>Профиль пользователя</b>",
        f"ID: <code>{user.telegram_id}</code>  | {name}",
        f"Регистрация: {user.created_at.strftime('%Y-%m-%d') if user.created_at else '-'}",
        f"Часовой пояс: {escape(user.timezone or 'UTC')}",
        "Состояние: "
        + (
            "забанен"
            if user.is_banned
            else ("авторизован" if user.is_authorized else "не авторизован")
        ),
        "",
        "<b>Всего</b>",
        f"Ответов: {total_attempts} | правильных: {total_correct} | точность: {pct(total_correct, total_attempts)}",
        f"Среднее время ответа: {avg_time_ms / 1000:.1f}s" if avg_time_ms else "Среднее время: -",
        f"Стрик: текущий {user.current_streak} | макс {user.max_streak}",
        f"Запусков /start: {user.total_starts}",
        f"Закладок: {bookmarks_count} | ачивок: {achievements_count}",
        "",
        "<b>Активность</b>",
        f"За 7 дней: {week_attempts} ответов, точность {pct(week_correct, week_attempts)}",
        f"За 30 дней: {month_attempts} ответов, активных дней {active_days}",
        "Последний ответ: "
        + (last_attempt_at.strftime('%Y-%m-%d %H:%M UTC') if last_attempt_at else "-"),
        "",
        f"<b>Mock-собесы:</b> завершено {mock_finished}"
        + (
            f", средний балл {pct(mock_correct, mock_total)} ({mock_correct}/{mock_total})"
            if mock_total
            else ""
        ),
        f"<b>Челлендж дня:</b> попыток {daily_attempts}, точность {pct(daily_correct, daily_attempts)}",
    ]

    if topic_rows:
        lines.append("")
        lines.append("<b>По темам (топ-10):</b>")
        for row in topic_rows[:10]:
            topic_key = row[0]
            cnt = int(row[1] or 0)
            ok = int(row[2] or 0)
            lines.append(
                f"- {escape(display_name(topic_key))}: {cnt} отв, {pct(ok, cnt)} точн"
            )
        weak = [
            (row[0], int(row[1] or 0), int(row[2] or 0))
            for row in topic_rows
            if int(row[1] or 0) >= 5 and (int(row[2] or 0) / max(int(row[1] or 1), 1)) < 0.5
        ]
        if weak:
            lines.append("")
            lines.append("<b>Слабые темы (точность ниже 50%, минимум 5 ответов):</b>")
            for topic_key, cnt, ok in weak[:5]:
                lines.append(
                    f"- {escape(display_name(topic_key))}: {pct(ok, cnt)} ({ok}/{cnt})"
                )

    if allowed_topics:
        lines.append("")
        lines.append(
            f"<b>Открытые темы ({len(allowed_topics)}):</b> "
            + ", ".join(escape(display_name(k)) for k in allowed_topics)
        )
    else:
        lines.append("")
        lines.append("<b>Открытые темы:</b> все (по умолчанию)")

    return "\n".join(lines)

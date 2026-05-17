from datetime import UTC, date, datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.db.models import Question, User
from pylevelup.repositories import (
    DailyChallengeRepository,
    QuestionRepository,
    UserRepository,
)
from pylevelup.services.achievement_evaluator import evaluate_and_grant
from pylevelup.services.achievement_notify import notify_user_about_codes
from pylevelup.utils.edit import safe_edit_text
from pylevelup.utils.text import clean_text, format_code_block, render_with_code

router = Router(name="pylevelup_daily")


def _today() -> date:
    return datetime.now(UTC).date()


def _format_question(question: Question, today: date) -> str:
    parts: list[str] = [f"<b>Челлендж дня - {today.isoformat()}</b>", ""]
    parts.append(f"<b>{render_with_code(question.text)}</b>")
    code_block = format_code_block(question.code, question.code_language)
    if code_block:
        parts.append("")
        parts.append(code_block)
    parts.append("")
    for index, option in enumerate(question.options):
        parts.append(f"{index + 1}. {render_with_code(option)}")
    return "\n".join(parts)


def _build_answer_keyboard(question_id: int, options_count: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    chunk: list[InlineKeyboardButton] = []
    for option_index in range(options_count):
        chunk.append(
            InlineKeyboardButton(
                text=f"{option_index + 1}",
                callback_data=f"daily:ans:{question_id}:{option_index}",
            )
        )
        if len(chunk) == 4:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)
    rows.append(
        [InlineKeyboardButton(text="Лидерборд", callback_data="daily:board")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Лидерборд дня", callback_data="daily:board")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:main")],
        ]
    )


async def _resolve_user(session_factory: async_sessionmaker, telegram_id: int) -> User | None:
    async with session_factory() as db:
        return await UserRepository(db).get_by_telegram_id(telegram_id)


async def _ensure_today_challenge(
    session_factory: async_sessionmaker, today: date
) -> Question | None:
    async with session_factory() as db:
        repo = DailyChallengeRepository(db)
        existing = await repo.get_for_date(today)
        if existing is not None:
            return await db.get(Question, existing.question_id)
    async with session_factory() as db:
        questions = await QuestionRepository(db).random_active(limit=1, topics=None)
        if not questions:
            return None
        chosen = questions[0]
        repo = DailyChallengeRepository(db)
        await repo.upsert_for_date(today, chosen.id)
        await db.commit()
        existing = await repo.get_for_date(today)
        if existing is None:
            return None
        return await db.get(Question, existing.question_id)


async def _challenge_content(
    session_factory: async_sessionmaker,
    telegram_id: int,
) -> tuple[str, InlineKeyboardMarkup] | None:
    today = _today()
    user = await _resolve_user(session_factory, telegram_id)
    if user is None:
        return None
    question = await _ensure_today_challenge(session_factory, today)
    if question is None:
        return (
            "Не удалось подобрать вопрос для челленджа. Попробуй позже.",
            _build_result_keyboard(),
        )
    async with session_factory() as db:
        repo = DailyChallengeRepository(db)
        attempt = await repo.get_attempt(user.id, today)
    if attempt is not None:
        return await _result_content(session_factory, user.id, question, today)
    return (
        _format_question(question, today),
        _build_answer_keyboard(question.id, len(question.options)),
    )


async def _result_content(
    session_factory: async_sessionmaker,
    user_id: int,
    question: Question,
    today: date,
) -> tuple[str, InlineKeyboardMarkup]:
    async with session_factory() as db:
        repo = DailyChallengeRepository(db)
        attempt = await repo.get_attempt(user_id, today)
        rank = await repo.user_rank(today, user_id) if attempt and attempt.is_correct else None
        total, correct = await repo.stats(today)
    if attempt is None:
        return "Челлендж ещё не пройден.", _build_result_keyboard()
    parts: list[str] = [f"<b>Челлендж дня - {today.isoformat()}</b>", ""]
    parts.append(f"<b>{render_with_code(question.text)}</b>")
    parts.append("")
    parts.append(
        f"Правильный ответ: <b>{question.correct_index + 1}</b>. {render_with_code(question.options[question.correct_index])}"
    )
    parts.append("")
    if attempt.is_correct:
        rank_label = f"#{rank}" if rank else "?"
        parts.append(f"Ты ответил <b>верно</b>. Твоё место: {rank_label} из {correct}.")
    else:
        parts.append("Ты ответил <b>неверно</b>. Завтра новый шанс.")
    parts.append(f"Всего попыток сегодня: {total}, правильных: {correct}.")
    if question.explanation:
        parts.append("")
        parts.append("<b>Пояснение</b>")
        parts.append(escape(clean_text(question.explanation)))
    return "\n".join(parts), _build_result_keyboard()


async def _leaderboard_content(
    session_factory: async_sessionmaker,
) -> tuple[str, InlineKeyboardMarkup]:
    today = _today()
    async with session_factory() as db:
        repo = DailyChallengeRepository(db)
        top = await repo.list_top_correct(today, limit=10)
        total, correct = await repo.stats(today)
    if not top:
        return (
            f"<b>Лидерборд дня - {today.isoformat()}</b>\n\nПока никто не дал правильный ответ. Будь первым.",
            _build_result_keyboard(),
        )
    lines = [f"<b>Лидерборд дня - {today.isoformat()}</b>", ""]
    for rank, (user, response_ms) in enumerate(top, start=1):
        name = escape(user.username or user.first_name or f"id{user.telegram_id}")
        if response_ms is None:
            time_str = "-"
        else:
            time_str = f"{response_ms / 1000:.1f}s"
        lines.append(f"{rank}. @{name} - {time_str}")
    lines.append("")
    lines.append(f"Правильных: {correct} из {total} попыток.")
    return "\n".join(lines), _build_result_keyboard()


@router.message(Command("daily"))
async def handle_daily_command(
    message: Message,
    session_factory: async_sessionmaker,
) -> None:
    if message.from_user is None:
        return
    content = await _challenge_content(session_factory, message.from_user.id)
    if content is None:
        await message.answer("Сначала /start.")
        return
    text, markup = content
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "daily:show")
async def handle_daily_show(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.from_user is None or call.message is None:
        await call.answer()
        return
    await call.answer()
    content = await _challenge_content(session_factory, call.from_user.id)
    if content is None:
        await call.message.answer("Сначала /start.")
        return
    text, markup = content
    await safe_edit_text(call.message, text, reply_markup=markup)


@router.callback_query(F.data == "daily:board")
async def handle_daily_board(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.message is None:
        await call.answer()
        return
    await call.answer()
    text, markup = await _leaderboard_content(session_factory)
    await safe_edit_text(call.message, text, reply_markup=markup)


@router.callback_query(F.data.startswith("daily:ans:"))
async def handle_daily_answer(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    bot: Bot,
) -> None:
    if call.from_user is None or call.message is None or call.data is None:
        await call.answer()
        return
    parts = call.data.split(":", 3)
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await call.answer()
        return
    question_id = int(parts[2])
    chosen = int(parts[3])
    today = _today()

    user = await _resolve_user(session_factory, call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return

    async with session_factory() as db:
        question = await db.get(Question, question_id)
    if question is None:
        await call.answer("Вопрос недоступен", show_alert=True)
        return

    is_correct = chosen == question.correct_index

    async with session_factory() as db:
        repo = DailyChallengeRepository(db)
        if await repo.has_attempted(user.id, today):
            await call.answer("Сегодня уже отвечал", show_alert=True)
            text, markup = await _result_content(session_factory, user.id, question, today)
            await safe_edit_text(call.message, text, reply_markup=markup)
            return
        await repo.record_attempt(user.id, today, is_correct, response_time_ms=None)
        await db.commit()

    await call.answer("Верно" if is_correct else "Неверно")
    text, markup = await _result_content(session_factory, user.id, question, today)
    await safe_edit_text(call.message, text, reply_markup=markup)

    async with session_factory() as db:
        new_codes = await evaluate_and_grant(db, user.id)
        await db.commit()
    if new_codes:
        await notify_user_about_codes(bot, call.from_user.id, new_codes)


__all__ = ["router"]

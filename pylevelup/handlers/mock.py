from datetime import UTC, datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.db.models import Question, User
from pylevelup.repositories import (
    MockSessionRepository,
    QuestionRepository,
    UserRepository,
)
from pylevelup.services.achievement_evaluator import evaluate_and_grant
from pylevelup.services.achievement_notify import notify_user_about_codes
from pylevelup.states import MockStates
from pylevelup.utils.text import clean_text

router = Router(name="pylevelup_mock")

MOCK_TOTAL_QUESTIONS = 20
MOCK_TIME_LIMIT_SECONDS = 30 * 60
MOCK_PASS_THRESHOLD = 0.7


def _intro_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Начать ({MOCK_TOTAL_QUESTIONS} вопросов, 30 мин)", callback_data="mock:start")],
            [InlineKeyboardButton(text="История попыток", callback_data="mock:history")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:main")],
        ]
    )


def _question_keyboard(question_id: int, options_count: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    chunk: list[InlineKeyboardButton] = []
    for option_index in range(options_count):
        chunk.append(
            InlineKeyboardButton(
                text=f"{option_index + 1}",
                callback_data=f"mock:ans:{question_id}:{option_index}",
            )
        )
        if len(chunk) == 4:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)
    rows.append([InlineKeyboardButton(text="Завершить досрочно", callback_data="mock:stop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ещё попытка", callback_data="mock:start")],
            [InlineKeyboardButton(text="История попыток", callback_data="mock:history")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:main")],
        ]
    )


async def _resolve_user(session_factory: async_sessionmaker, telegram_id: int) -> User | None:
    async with session_factory() as db:
        return await UserRepository(db).get_by_telegram_id(telegram_id)


def _format_question(question: Question, position: int, total: int, deadline: datetime) -> str:
    remaining = max(0, int((deadline - datetime.now(UTC)).total_seconds()))
    minutes, seconds = divmod(remaining, 60)
    parts: list[str] = [
        f"<i>Mock-собес #{position} из {total} (осталось {minutes:02d}:{seconds:02d})</i>",
        "",
        f"<b>{escape(clean_text(question.text))}</b>",
        "",
    ]
    for index, option in enumerate(question.options):
        parts.append(f"{index + 1}. {escape(clean_text(option))}")
    return "\n".join(parts)


async def _send_question(
    target: Message,
    session_factory: async_sessionmaker,
    question_id: int,
    position: int,
    total: int,
    deadline: datetime,
) -> None:
    async with session_factory() as db:
        question = await db.get(Question, question_id)
    if question is None:
        await target.answer("Не нашёл вопрос. Завершаю.")
        return
    await target.answer(
        _format_question(question, position, total, deadline),
        reply_markup=_question_keyboard(question.id, len(question.options)),
    )


async def _start_session(
    target: Message,
    state: FSMContext,
    session_factory: async_sessionmaker,
) -> None:
    async with session_factory() as db:
        repo = QuestionRepository(db)
        questions = await repo.random_active(limit=MOCK_TOTAL_QUESTIONS, topics=None)
    if len(questions) < MOCK_TOTAL_QUESTIONS:
        await target.answer("Недостаточно вопросов в базе для mock-собеса.")
        return
    started_at = datetime.now(UTC)
    deadline = datetime.fromtimestamp(
        started_at.timestamp() + MOCK_TIME_LIMIT_SECONDS, tz=UTC
    )
    queue = [q.id for q in questions]
    answers: list[dict] = []
    await state.set_state(MockStates.in_session)
    await state.update_data(
        mock_queue=queue,
        mock_index=0,
        mock_answers=answers,
        mock_started_at=started_at.isoformat(),
        mock_deadline=deadline.isoformat(),
    )
    await target.answer(
        f"<b>Mock-собес запущен.</b>\n"
        f"{MOCK_TOTAL_QUESTIONS} вопросов из всех тем, лимит 30 минут.\n"
        f"Удачи!"
    )
    await _send_question(target, session_factory, queue[0], 1, MOCK_TOTAL_QUESTIONS, deadline)


async def _finish_session(
    target: Message,
    state: FSMContext,
    session_factory: async_sessionmaker,
    telegram_id: int,
    by_timeout: bool,
    bot: Bot | None = None,
) -> None:
    data = await state.get_data()
    queue: list[int] = data.get("mock_queue") or []
    answers: list[dict] = data.get("mock_answers") or []
    started_at_iso: str | None = data.get("mock_started_at")
    if not queue or not started_at_iso:
        await state.clear()
        await target.answer("Mock-сессия не найдена.")
        return
    started_at = datetime.fromisoformat(started_at_iso)
    finished_at = datetime.now(UTC)
    duration = max(1, int((finished_at - started_at).total_seconds()))

    user = await _resolve_user(session_factory, telegram_id)
    if user is None:
        await state.clear()
        await target.answer("Сначала /start.")
        return

    answered_ids = [a["question_id"] for a in answers]
    async with session_factory() as db:
        questions = await QuestionRepository(db).get_many(answered_ids)
    by_id = {q.id: q for q in questions}

    breakdown_correct: dict[str, int] = {}
    breakdown_total: dict[str, int] = {}
    correct_count = 0
    for entry in answers:
        question = by_id.get(entry["question_id"])
        if question is None:
            continue
        topic = question.topic
        breakdown_total[topic] = breakdown_total.get(topic, 0) + 1
        if entry["is_correct"]:
            breakdown_correct[topic] = breakdown_correct.get(topic, 0) + 1
            correct_count += 1

    total_answered = len(answers)
    accuracy = (correct_count / total_answered) if total_answered else 0.0
    passed = accuracy >= MOCK_PASS_THRESHOLD and total_answered >= MOCK_TOTAL_QUESTIONS

    breakdown = {
        topic: {
            "correct": breakdown_correct.get(topic, 0),
            "total": breakdown_total[topic],
        }
        for topic in breakdown_total
    }

    async with session_factory() as db:
        await MockSessionRepository(db).create(
            user_id=user.id,
            total_questions=total_answered,
            correct_count=correct_count,
            duration_seconds=duration,
            breakdown=breakdown,
            passed=passed,
            finished_at=finished_at,
        )
        await db.commit()

    minutes, seconds = divmod(duration, 60)
    suffix = " (по таймауту)" if by_timeout else ""
    parts: list[str] = [
        f"<b>Mock-собес завершён{suffix}</b>",
        "",
        f"Вопросов отвечено: {total_answered} из {MOCK_TOTAL_QUESTIONS}",
        f"Правильных: {correct_count} ({accuracy * 100:.0f}%)",
        f"Время: {minutes:02d}:{seconds:02d}",
        f"Результат: <b>{'прошёл' if passed else 'не прошёл'}</b> (порог {int(MOCK_PASS_THRESHOLD * 100)}%)",
        "",
    ]
    if breakdown:
        parts.append("<b>По темам:</b>")
        for topic, stats in sorted(
            breakdown.items(),
            key=lambda x: (x[1]["correct"] / x[1]["total"]) if x[1]["total"] else 0,
        ):
            t_acc = (stats["correct"] / stats["total"]) if stats["total"] else 0
            parts.append(
                f"  {escape(topic)}: {stats['correct']}/{stats['total']} "
                f"({t_acc * 100:.0f}%)"
            )

    await state.clear()
    await target.answer("\n".join(parts), reply_markup=_result_keyboard())

    async with session_factory() as db:
        new_codes = await evaluate_and_grant(db, user.id)
        await db.commit()
    if new_codes and bot is not None:
        await notify_user_about_codes(bot, telegram_id, new_codes)


@router.message(Command("mock"))
async def handle_mock_command(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer(
        f"<b>Mock-собеседование</b>\n\n"
        f"{MOCK_TOTAL_QUESTIONS} случайных вопросов из всех тем.\n"
        f"Лимит времени: 30 минут.\n"
        f"Порог сдачи: {int(MOCK_PASS_THRESHOLD * 100)}%.",
        reply_markup=_intro_keyboard(),
    )


@router.callback_query(F.data == "mock:show")
async def handle_mock_show(
    call: CallbackQuery,
    state: FSMContext,
) -> None:
    if call.message is None:
        await call.answer()
        return
    await state.clear()
    await call.answer()
    await call.message.answer(
        f"<b>Mock-собеседование</b>\n\n"
        f"{MOCK_TOTAL_QUESTIONS} случайных вопросов из всех тем.\n"
        f"Лимит времени: 30 минут.\n"
        f"Порог сдачи: {int(MOCK_PASS_THRESHOLD * 100)}%.",
        reply_markup=_intro_keyboard(),
    )


@router.callback_query(F.data == "mock:start")
async def handle_mock_start(
    call: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker,
) -> None:
    if call.message is None:
        await call.answer()
        return
    await call.answer()
    await _start_session(call.message, state, session_factory)


@router.callback_query(F.data == "mock:stop", MockStates.in_session)
async def handle_mock_stop(
    call: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker,
    bot: Bot,
) -> None:
    if call.message is None or call.from_user is None:
        await call.answer()
        return
    await call.answer()
    await _finish_session(
        call.message, state, session_factory, call.from_user.id, by_timeout=False, bot=bot
    )


@router.callback_query(F.data.startswith("mock:ans:"), MockStates.in_session)
async def handle_mock_answer(
    call: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker,
    bot: Bot,
) -> None:
    if call.message is None or call.from_user is None or call.data is None:
        await call.answer()
        return
    parts = call.data.split(":", 3)
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await call.answer()
        return
    question_id = int(parts[2])
    chosen = int(parts[3])

    data = await state.get_data()
    queue: list[int] = data.get("mock_queue") or []
    index: int = int(data.get("mock_index") or 0)
    answers: list[dict] = list(data.get("mock_answers") or [])
    deadline_iso: str | None = data.get("mock_deadline")
    if not queue or not deadline_iso:
        await call.answer()
        return
    if index >= len(queue) or queue[index] != question_id:
        await call.answer("Этот вопрос уже не активен", show_alert=True)
        return
    deadline = datetime.fromisoformat(deadline_iso)

    async with session_factory() as db:
        question = await db.get(Question, question_id)
    if question is None:
        await call.answer("Вопрос недоступен", show_alert=True)
        return

    is_correct = chosen == question.correct_index
    answers.append(
        {
            "question_id": question_id,
            "chosen": chosen,
            "is_correct": is_correct,
        }
    )
    next_index = index + 1
    await state.update_data(mock_answers=answers, mock_index=next_index)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await call.answer("Верно" if is_correct else "Неверно")

    now = datetime.now(UTC)
    if next_index >= len(queue):
        await _finish_session(
            call.message, state, session_factory, call.from_user.id, by_timeout=False, bot=bot
        )
        return
    if now >= deadline:
        await _finish_session(
            call.message, state, session_factory, call.from_user.id, by_timeout=True, bot=bot
        )
        return
    await _send_question(
        call.message,
        session_factory,
        queue[next_index],
        next_index + 1,
        len(queue),
        deadline,
    )


async def _show_history(
    target: Message,
    session_factory: async_sessionmaker,
    telegram_id: int,
) -> None:
    user = await _resolve_user(session_factory, telegram_id)
    if user is None:
        await target.answer("Сначала /start.")
        return
    async with session_factory() as db:
        sessions = await MockSessionRepository(db).list_for_user(user.id, limit=5)
    if not sessions:
        await target.answer("Mock-собеседований ещё не было.")
        return
    lines: list[str] = ["<b>Последние mock-собеседования</b>", ""]
    for s in sessions:
        accuracy = (s.correct_count / s.total_questions * 100) if s.total_questions else 0
        verdict = "прошёл" if s.passed else "не прошёл"
        duration_min = (s.duration_seconds or 0) // 60
        lines.append(
            f"{s.created_at.date().isoformat()} - {s.correct_count}/{s.total_questions} "
            f"({accuracy:.0f}%, {duration_min} мин) - {verdict}"
        )
    await target.answer(
        "\n".join(lines),
        reply_markup=_intro_keyboard(),
    )


@router.callback_query(F.data == "mock:history")
async def handle_mock_history(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.message is None or call.from_user is None:
        await call.answer()
        return
    await call.answer()
    await _show_history(call.message, session_factory, call.from_user.id)


__all__ = ["router"]

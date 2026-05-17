from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pylevelup.categories import display_name
from pylevelup.db.models import Attempt, LearningPath, Question
from pylevelup.repositories import (
    LearningPathRepository,
    UserPathProgressRepository,
    UserRepository,
)
from pylevelup.utils.edit import edit_or_send, safe_edit_text

router = Router(name="pylevelup_learning_paths")


async def _topic_stats(db: AsyncSession, user_id: int, topic_key: str) -> tuple[int, int]:
    correct_expr = func.sum(case((Attempt.is_correct, 1), else_=0))
    stmt = (
        select(
            func.count(Attempt.id).label("total"),
            correct_expr.label("correct"),
        )
        .select_from(Attempt)
        .join(Question, Question.id == Attempt.question_id)
        .where(Attempt.user_id == user_id, Question.topic == topic_key)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return 0, 0
    total = int(row.total or 0)
    correct = int(row.correct or 0)
    return total, correct


def _is_step_done(answered: int, correct: int, req_q: int, req_acc: int) -> bool:
    if answered < req_q:
        return False
    if answered == 0:
        return False
    accuracy = correct / answered * 100
    return accuracy >= req_acc - 0.001


async def _compute_current_position(
    db: AsyncSession, user_id: int, path: LearningPath
) -> tuple[int, bool]:
    steps = sorted(path.steps, key=lambda s: s.position)
    for idx, step in enumerate(steps):
        answered, correct = await _topic_stats(db, user_id, step.topic_key)
        if not _is_step_done(
            answered, correct, step.required_questions, step.required_accuracy
        ):
            return idx, False
    return len(steps), True


def _paths_list_kb(paths: list[LearningPath]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not paths:
        rows.append(
            [InlineKeyboardButton(text="Учебные планы пока не созданы", callback_data="lp:noop")]
        )
    for p in paths:
        rows.append(
            [InlineKeyboardButton(text=p.title, callback_data=f"lp:view:{p.id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("paths"))
async def handle_paths_cmd(
    message: Message,
    session_factory: async_sessionmaker,
    state: FSMContext,
) -> None:
    await state.clear()
    if message.from_user is None:
        return
    async with session_factory() as db:
        paths = await LearningPathRepository(db).list_active()
    text = (
        "<b>Учебные планы</b>\n\n"
        "Это последовательные курсы. У каждого блока свой порог: сколько вопросов решить и с какой точностью. "
        "Прошёл блок - открывается следующий.\n"
        "Выбери план:"
    )
    await message.answer(text, reply_markup=_paths_list_kb(paths))


@router.callback_query(F.data == "lp:list")
async def handle_paths_list(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.message is None:
        await call.answer()
        return
    async with session_factory() as db:
        paths = await LearningPathRepository(db).list_active()
    await call.answer()
    await safe_edit_text(
        call.message,
        "<b>Учебные планы</b>\n\nВыбери план:",
        reply_markup=_paths_list_kb(paths),
    )


@router.callback_query(F.data == "lp:noop")
async def handle_noop(call: CallbackQuery) -> None:
    await call.answer()


def _path_view_kb(
    path: LearningPath, current_pos: int, completed: bool
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    steps = sorted(path.steps, key=lambda s: s.position)
    if not completed and current_pos < len(steps):
        step = steps[current_pos]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"▶️ Тренировать: {step.title or display_name(step.topic_key)}",
                    callback_data=f"lp:start:{path.id}:{step.id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="🔄 Обновить прогресс", callback_data=f"lp:view:{path.id}")]
    )
    rows.append([InlineKeyboardButton(text="<< К планам", callback_data="lp:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_path(
    db: AsyncSession,
    user_id: int,
    path: LearningPath,
) -> tuple[str, int, bool]:
    steps = sorted(path.steps, key=lambda s: s.position)
    if not steps:
        return (
            f"<b>{escape(path.title)}</b>\n\nВ этом плане ещё нет блоков.",
            0,
            False,
        )

    current_pos, completed = await _compute_current_position(db, user_id, path)

    lines: list[str] = [f"<b>{escape(path.title)}</b>"]
    if path.description:
        lines.append(escape(path.description))
    lines.append("")
    lines.append(f"Прогресс: {current_pos}/{len(steps)} блоков")
    if completed:
        lines.append("🎉 <b>План полностью пройден!</b>")
    lines.append("")

    for idx, step in enumerate(steps):
        answered, correct = await _topic_stats(db, user_id, step.topic_key)
        acc = (correct / answered * 100) if answered else 0
        topic_label = escape(step.title or display_name(step.topic_key))
        if idx < current_pos:
            icon = "✅"
        elif idx == current_pos and not completed:
            icon = "🔵"
        else:
            icon = "🔒"
        progress_part = (
            f"{answered}/{step.required_questions} вопросов, "
            f"точность {acc:.0f}% (нужно {step.required_accuracy}%)"
        )
        lines.append(f"{icon} <b>Блок {idx + 1}.</b> {topic_label}")
        lines.append(f"    {progress_part}")

    return "\n".join(lines), current_pos, completed


@router.callback_query(F.data.startswith("lp:view:"))
async def handle_path_view(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.message is None or call.data is None or call.from_user is None:
        await call.answer()
        return
    try:
        path_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        user = await UserRepository(db).get_by_telegram_id(call.from_user.id)
        if user is None:
            await call.answer("Сначала запусти /start", show_alert=True)
            return
        path = await LearningPathRepository(db).get(path_id)
        if path is None:
            await call.answer("План не найден", show_alert=True)
            return
        text, current_pos, completed = await _render_path(db, user.id, path)
        await UserPathProgressRepository(db).advance(
            user.id, path.id, current_pos, completed
        )
        await db.commit()
    await call.answer()
    await safe_edit_text(call.message, text, reply_markup=_path_view_kb(path, current_pos, completed))


@router.callback_query(F.data.startswith("lp:start:"))
async def handle_path_start(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.message is None or call.data is None:
        await call.answer()
        return
    parts = call.data.split(":")
    if len(parts) != 4:
        await call.answer()
        return
    try:
        path_id = int(parts[2])
        step_id = int(parts[3])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        path = await LearningPathRepository(db).get(path_id)
    if path is None:
        await call.answer("План не найден", show_alert=True)
        return
    step = next((s for s in path.steps if s.id == step_id), None)
    if step is None:
        await call.answer("Блок не найден", show_alert=True)
        return
    await call.answer()
    topic = display_name(step.topic_key)
    text = (
        f"<b>Блок:</b> {escape(step.title or topic)}\n\n"
        f"Тема: <code>{escape(step.topic_key)}</code>\n"
        f"Цель: решить {step.required_questions} вопросов с точностью ≥ {step.required_accuracy}%.\n\n"
        "Запусти тренажёр командой:\n"
        f"<code>/test</code> → выбери тему «{escape(topic)}»\n\n"
        "Или нажми кнопку ниже и затем выбери тему в стандартном меню."
    )
    rows = [
        [InlineKeyboardButton(text="▶️ Открыть /test", callback_data="lp:opentest")],
        [InlineKeyboardButton(text="<< К плану", callback_data=f"lp:view:{path_id}")],
    ]
    await edit_or_send(call.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "lp:opentest")
async def handle_open_test(
    call: CallbackQuery,
) -> None:
    if call.message is None:
        await call.answer()
        return
    await call.answer()
    await call.message.answer("Введи /test чтобы открыть тренажёр.")

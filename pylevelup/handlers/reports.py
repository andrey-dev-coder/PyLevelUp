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

from pylevelup.categories import display_name
from pylevelup.config import Settings
from pylevelup.db.models import Question, QuestionReport, User
from pylevelup.repositories import (
    QuestionReportRepository,
    QuestionRepository,
    UserRepository,
)
from pylevelup.states import ReportStates
from pylevelup.utils.edit import safe_edit_text
from pylevelup.utils.text import clean_text, render_with_code

router = Router(name="pylevelup_reports")

MAX_REASON_LEN = 500


def _is_owner(actor_id: int, settings: Settings) -> bool:
    return actor_id == settings.owner_telegram_id


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:main")]
        ]
    )


def _report_resolution_keyboard(report_id: int, question_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Решено",
                    callback_data=f"rep:done:{report_id}",
                ),
                InlineKeyboardButton(
                    text="Скрыть вопрос",
                    callback_data=f"rep:hide:{report_id}:{question_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Следующая жалоба",
                    callback_data="reports:next",
                ),
                InlineKeyboardButton(
                    text="В главное меню",
                    callback_data="menu:main",
                ),
            ],
        ]
    )


def _format_report_entry(
    report: QuestionReport,
    question: Question | None,
    author_username: str | None,
) -> str:
    parts: list[str] = [
        f"<b>Жалоба #{report.id}</b>",
        f"От: {escape(author_username or str(report.user_id))}",
        f"Когда: {report.created_at:%Y-%m-%d %H:%M UTC}",
        f"Причина: {render_with_code(report.reason)}",
        "",
    ]
    if question is None:
        parts.append("<i>Вопрос удалён или недоступен.</i>")
        return "\n".join(parts)
    parts.append(f"<b>Вопрос #{question.id} [{display_name(question.topic)}]</b>")
    parts.append(render_with_code(question.text))
    parts.append("")
    for idx, option in enumerate(question.options):
        marker = "✅" if idx == question.correct_index else "▫️"
        parts.append(f"{marker} {render_with_code(option)}")
    if question.explanation:
        parts.append("")
        parts.append(f"<i>{render_with_code(clean_text(question.explanation))}</i>")
    return "\n".join(parts)


@router.callback_query(F.data.startswith("report:open:"))
async def handle_report_open(
    call: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker,
) -> None:
    if call.message is None or call.data is None or call.from_user is None:
        await call.answer()
        return
    try:
        question_id = int(call.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await call.answer()
        return
    async with session_factory() as db:
        user = await UserRepository(db).get_by_telegram_id(call.from_user.id)
        if user is None:
            await call.answer("Сначала зарегистрируйся через /start", show_alert=True)
            return
        repo = QuestionReportRepository(db)
        if await repo.has_recent_for_user(user.id, question_id):
            await call.answer("Ты уже репортнул этот вопрос", show_alert=True)
            return
    await state.set_state(ReportStates.awaiting_reason)
    await state.update_data(report_question_id=question_id)
    await call.answer()
    await call.message.answer(
        "Опиши, что не так с вопросом (опечатка, неверный ответ, плохая формулировка).\n"
        f"До {MAX_REASON_LEN} символов. Отмена - /cancel."
    )


@router.message(ReportStates.awaiting_reason, Command("cancel"))
async def handle_report_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Жалоба отменена.")


@router.message(ReportStates.awaiting_reason)
async def handle_report_reason(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
    bot: Bot,
) -> None:
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("Пустая причина. Опиши проблему или /cancel.")
        return
    if len(reason) > MAX_REASON_LEN:
        reason = reason[:MAX_REASON_LEN]
    data = await state.get_data()
    question_id = data.get("report_question_id")
    if not isinstance(question_id, int):
        await state.clear()
        await message.answer("Не получилось привязать жалобу к вопросу. Попробуй ещё раз.")
        return
    if message.from_user is None:
        await state.clear()
        return
    async with session_factory() as db:
        user = await UserRepository(db).get_by_telegram_id(message.from_user.id)
        if user is None:
            await state.clear()
            await message.answer("Сначала /start.")
            return
        repo = QuestionReportRepository(db)
        report = await repo.create(user.id, question_id, reason)
        await db.commit()
        question = await QuestionRepository(db).get_by_id(question_id)
    await state.clear()
    await message.answer(
        f"Жалоба принята (#{report.id}). Спасибо - я разберу и поправлю.",
        reply_markup=_back_keyboard(),
    )
    if settings.owner_telegram_id and settings.owner_telegram_id != message.from_user.id:
        owner_text = _format_report_entry(
            report, question, message.from_user.username
        )
        try:
            await bot.send_message(
                settings.owner_telegram_id,
                owner_text,
                reply_markup=_report_resolution_keyboard(report.id, question_id),
            )
        except Exception:
            pass


@router.message(Command("reports"))
async def handle_reports_command(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None or not _is_owner(message.from_user.id, settings):
        return
    async with session_factory() as db:
        repo = QuestionReportRepository(db)
        total = await repo.count_open()
        items = await repo.list_open(limit=1)
        question = None
        author = None
        if items:
            question = await QuestionRepository(db).get_by_id(items[0].question_id)
            user = await db.get(User, items[0].user_id)
            author = user.username if user is not None else None
    if total == 0:
        await message.answer(
            "Открытых жалоб нет.",
            reply_markup=_back_keyboard(),
        )
        return
    text = (
        f"<b>Жалобы (открытых: {total})</b>\n\n"
        + _format_report_entry(items[0], question, author)
    )
    await message.answer(
        text,
        reply_markup=_report_resolution_keyboard(items[0].id, items[0].question_id),
    )


@router.callback_query(F.data == "reports:next")
async def handle_reports_next(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if call.from_user is None or not _is_owner(call.from_user.id, settings):
        await call.answer()
        return
    if call.message is None:
        await call.answer()
        return
    await call.answer()
    async with session_factory() as db:
        repo = QuestionReportRepository(db)
        total = await repo.count_open()
        items = await repo.list_open(limit=1)
        question = None
        author = None
        if items:
            question = await QuestionRepository(db).get_by_id(items[0].question_id)
            user = await db.get(User, items[0].user_id)
            author = user.username if user is not None else None
    if not items:
        await safe_edit_text(
            call.message,
            "Открытых жалоб больше нет.",
            reply_markup=_back_keyboard(),
        )
        return
    text = (
        f"<b>Жалобы (открытых: {total})</b>\n\n"
        + _format_report_entry(items[0], question, author)
    )
    await safe_edit_text(
        call.message,
        text,
        reply_markup=_report_resolution_keyboard(items[0].id, items[0].question_id),
    )


@router.callback_query(F.data.startswith("rep:done:"))
async def handle_report_done(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if call.from_user is None or not _is_owner(call.from_user.id, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    try:
        report_id = int(call.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await call.answer()
        return
    async with session_factory() as db:
        repo = QuestionReportRepository(db)
        await repo.resolve(report_id, "resolved")
        await db.commit()
    await call.answer("Жалоба закрыта")
    await handle_reports_next(call, session_factory, settings)


@router.callback_query(F.data.startswith("rep:hide:"))
async def handle_report_hide(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if call.from_user is None or not _is_owner(call.from_user.id, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    parts = call.data.split(":")
    if len(parts) < 4:
        await call.answer()
        return
    try:
        report_id = int(parts[2])
        question_id = int(parts[3])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        question = await QuestionRepository(db).get_by_id(question_id)
        if question is not None:
            question.is_active = False
        repo = QuestionReportRepository(db)
        await repo.resolve(report_id, "hidden")
        await db.commit()
    await call.answer("Вопрос скрыт")
    await handle_reports_next(call, session_factory, settings)


__all__ = ["router"]

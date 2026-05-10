from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.categories import display_name
from pylevelup.db.models import OpenQuestion
from pylevelup.repositories import OpenQuestionRepository
from pylevelup.utils.edit import safe_edit_text
from pylevelup.utils.text import render_with_code

router = Router(name="pylevelup_open_questions")


def _format_question(question: OpenQuestion) -> str:
    return (
        f"<i>Открытый вопрос - {display_name(question.topic)}</i>\n\n"
        f"<b>{render_with_code(question.text)}</b>\n\n"
        "Сформулируй ответ для себя (можно вслух или мысленно), "
        "потом нажми <b>Показать ответ</b> для разбора."
    )


def _format_answer(question: OpenQuestion) -> str:
    parts: list[str] = [
        f"<i>Открытый вопрос - {display_name(question.topic)}</i>",
        "",
        f"<b>{render_with_code(question.text)}</b>",
        "",
        "<b>Эталонный ответ</b>",
        render_with_code(question.ideal_answer),
    ]
    if question.checklist:
        parts.append("")
        parts.append("<b>Чек-лист пунктов</b>")
        for item in question.checklist:
            parts.append(f"- {render_with_code(item)}")
    return "\n".join(parts)


def _question_keyboard(question_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Показать ответ",
                    callback_data=f"open:show:{question_id}",
                )
            ],
            [
                InlineKeyboardButton(text="Следующий", callback_data="open:next"),
                InlineKeyboardButton(text="В меню", callback_data="menu:main"),
            ],
        ]
    )


def _answer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Следующий вопрос", callback_data="open:next")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:main")],
        ]
    )


async def _pick_random(session_factory: async_sessionmaker) -> OpenQuestion | None:
    async with session_factory() as db:
        return await OpenQuestionRepository(db).random_active()


@router.message(Command("open"))
async def handle_open_command(
    message: Message,
    session_factory: async_sessionmaker,
) -> None:
    question = await _pick_random(session_factory)
    if question is None:
        await message.answer("Открытых вопросов пока нет. Загляни позже.")
        return
    await message.answer(_format_question(question), reply_markup=_question_keyboard(question.id))


@router.callback_query(F.data == "open:show_random")
async def handle_open_show_random(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.message is None:
        await call.answer()
        return
    question = await _pick_random(session_factory)
    await call.answer()
    if question is None:
        await safe_edit_text(call.message, "Открытых вопросов пока нет. Загляни позже.")
        return
    await safe_edit_text(
        call.message,
        _format_question(question),
        reply_markup=_question_keyboard(question.id),
    )


@router.callback_query(F.data == "open:next")
async def handle_open_next(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    await handle_open_show_random(call, session_factory)


@router.callback_query(F.data.startswith("open:show:"))
async def handle_open_show_answer(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.message is None or call.data is None:
        await call.answer()
        return
    try:
        question_id = int(call.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await call.answer()
        return
    async with session_factory() as db:
        question = await OpenQuestionRepository(db).get(question_id)
    if question is None:
        await call.answer("Вопрос недоступен", show_alert=True)
        return
    await call.answer()
    await safe_edit_text(
        call.message,
        _format_answer(question),
        reply_markup=_answer_keyboard(),
    )


__all__ = ["router"]

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.categories import display_name
from pylevelup.repositories import QuestionRepository
from pylevelup.states import SearchStates
from pylevelup.utils.edit import safe_edit_text
from pylevelup.utils.text import clean_text, render_with_code

router = Router(name="pylevelup_search")

MAX_RESULTS = 10
SNIPPET_LIMIT = 160


def _prompt_text() -> str:
    return (
        "<b>Поиск по вопросам</b>\n\n"
        "Пришли следующим сообщением одно или несколько ключевых слов. "
        "Например: <code>GIL</code>, <code>asyncio</code>, <code>JOIN</code>.\n\n"
        "Для отмены - /cancel."
    )


def _prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:main")]
        ]
    )


def _result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Новый поиск", callback_data="search:show")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:main")],
        ]
    )


async def _do_search(
    query: str,
    session_factory: async_sessionmaker,
) -> str:
    async with session_factory() as db:
        questions = await QuestionRepository(db).search(query, limit=MAX_RESULTS)
    if not questions:
        return (
            f"<b>Поиск:</b> <i>{render_with_code(query)}</i>\n\n"
            "Ничего не нашлось. Попробуй другие ключевые слова."
        )
    lines: list[str] = [
        f"<b>Поиск:</b> <i>{render_with_code(query)}</i>",
        f"Найдено: {len(questions)}",
        "",
    ]
    for index, q in enumerate(questions, start=1):
        snippet = clean_text(q.text)
        if len(snippet) > SNIPPET_LIMIT:
            snippet = snippet[:SNIPPET_LIMIT].rstrip() + "..."
        lines.append(f"<b>{index}. [{display_name(q.topic)}]</b>")
        lines.append(render_with_code(snippet))
        correct_option = q.options[q.correct_index] if q.options else ""
        lines.append(
            f"Ответ: <b>{q.correct_index + 1}</b>. {render_with_code(correct_option)}"
        )
        if q.explanation:
            exp = clean_text(q.explanation)
            if len(exp) > SNIPPET_LIMIT:
                exp = exp[:SNIPPET_LIMIT].rstrip() + "..."
            lines.append(f"<i>{render_with_code(exp)}</i>")
        lines.append("")
    return "\n".join(lines).rstrip()


@router.message(Command("search"))
async def handle_search_command(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session_factory: async_sessionmaker,
) -> None:
    if command.args and command.args.strip():
        await state.clear()
        text = await _do_search(command.args.strip(), session_factory)
        await message.answer(text, reply_markup=_result_keyboard())
        return
    await state.set_state(SearchStates.awaiting_query)
    await message.answer(_prompt_text(), reply_markup=_prompt_keyboard())


@router.callback_query(F.data == "search:show")
async def handle_search_show(call: CallbackQuery, state: FSMContext) -> None:
    if call.message is None:
        await call.answer()
        return
    await state.set_state(SearchStates.awaiting_query)
    await call.answer()
    await safe_edit_text(call.message, _prompt_text(), reply_markup=_prompt_keyboard())


@router.message(SearchStates.awaiting_query, Command("cancel"))
async def handle_search_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Поиск отменён.")


@router.message(SearchStates.awaiting_query)
async def handle_search_query(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker,
) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer("Пустой запрос. Пришли ключевые слова или /cancel.")
        return
    if len(query) < 2:
        await message.answer("Слишком короткий запрос. Минимум 2 символа.")
        return
    await state.clear()
    text = await _do_search(query, session_factory)
    await message.answer(text, reply_markup=_result_keyboard())


__all__ = ["router"]

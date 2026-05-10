from __future__ import annotations

from html import escape

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

from pylevelup.ai import AIError, AIUnavailable, get_ai_client
from pylevelup.ai.service import (
    check_quota,
    elaborate_question,
    free_form_answer,
    record_usage,
)
from pylevelup.config import Settings
from pylevelup.repositories import QuestionRepository, UserRepository
from pylevelup.states import AIStates
from pylevelup.utils.edit import safe_edit_text
from pylevelup.utils.text import clean_text, render_with_code

router = Router(name="pylevelup_ai_helper")

MAX_QUESTION_LEN = 600
MAX_REPLY_CHARS = 3200


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Спросить ещё", callback_data="ai:ask")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:main")],
        ]
    )


def _elaborate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Спросить ИИ", callback_data="ai:ask")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:main")],
        ]
    )


def _trim(text: str) -> str:
    if len(text) <= MAX_REPLY_CHARS:
        return text
    return text[: MAX_REPLY_CHARS - 3].rstrip() + "..."


def _format_ai_reply(title: str, body: str, provider: str) -> str:
    return (
        f"<b>{title}</b>\n\n"
        f"{render_with_code(_trim(body))}\n\n"
        f"<i>via {escape(provider)}</i>"
    )


async def _resolve_user_id(session_factory: async_sessionmaker, telegram_id: int) -> int | None:
    async with session_factory() as db:
        user = await UserRepository(db).get_by_telegram_id(telegram_id)
        return user.id if user is not None else None


async def _check_and_warn(
    target: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    telegram_id: int,
) -> int | None:
    user_id = await _resolve_user_id(session_factory, telegram_id)
    if user_id is None:
        await target.answer("Сначала пройди /start.")
        return None
    is_owner = telegram_id == settings.owner_telegram_id
    async with session_factory() as db:
        allowed, remaining = await check_quota(db, settings, user_id, is_owner)
    if not allowed:
        await target.answer(
            f"Дневной лимит ИИ-запросов исчерпан ({settings.ai_daily_limit_per_user} в день). "
            "Возвращайся завтра."
        )
        return None
    if not is_owner and remaining <= 3:
        await target.answer(
            f"<i>Осталось {remaining} ИИ-запросов на сегодня.</i>"
        )
    return user_id


@router.message(Command("ask"))
async def handle_ask_command(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    client = await get_ai_client()
    if not client.is_available():
        await message.answer("ИИ-помощник пока не настроен на сервере.")
        return
    raw = (command.args or "").strip()
    if not raw:
        await state.set_state(AIStates.awaiting_question)
        await message.answer(
            "Спроси что угодно про Python, БД, async, system design - "
            "коротко в одном сообщении. Отмена - /cancel."
        )
        return
    user_id = await _check_and_warn(message, session_factory, settings, message.from_user.id)
    if user_id is None:
        return
    await _run_free_form(message, user_id, raw, session_factory)


@router.callback_query(F.data == "ai:ask")
async def handle_ai_ask_callback(
    call: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker,
) -> None:
    if call.message is None or call.from_user is None:
        await call.answer()
        return
    client = await get_ai_client()
    if not client.is_available():
        await call.answer("ИИ-помощник пока не настроен", show_alert=True)
        return
    await call.answer()
    await state.set_state(AIStates.awaiting_question)
    await call.message.answer(
        "Спроси что угодно по теме - коротко в одном сообщении. Отмена - /cancel."
    )


@router.message(AIStates.awaiting_question, Command("cancel"))
async def handle_ai_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Окей, отменил.")


@router.message(AIStates.awaiting_question)
async def handle_ai_question(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Пустой запрос. Спроси что-нибудь или /cancel.")
        return
    if len(raw) > MAX_QUESTION_LEN:
        raw = raw[:MAX_QUESTION_LEN]
    user_id = await _check_and_warn(message, session_factory, settings, message.from_user.id)
    if user_id is None:
        await state.clear()
        return
    await state.clear()
    await _run_free_form(message, user_id, raw, session_factory)


async def _run_free_form(
    message: Message,
    user_id: int,
    question_text: str,
    session_factory: async_sessionmaker,
) -> None:
    placeholder = await message.answer("Думаю...")
    client = await get_ai_client()
    try:
        result = await free_form_answer(client, question_text)
    except AIUnavailable:
        await safe_edit_text(placeholder, "ИИ-помощник недоступен. Попробуй позже.")
        return
    except AIError as exc:
        await safe_edit_text(placeholder, f"Не получилось получить ответ от ИИ: {escape(str(exc)[:200])}")
        return
    async with session_factory() as db:
        await record_usage(db, user_id, "ask", result)
        await db.commit()
    title = clean_text(question_text)
    if len(title) > 120:
        title = title[:120].rstrip() + "..."
    await safe_edit_text(
        placeholder,
        _format_ai_reply(f"Вопрос: {escape(title)}", result.text, result.provider),
        reply_markup=_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("ai:more:"))
async def handle_ai_elaborate(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if call.message is None or call.from_user is None or call.data is None:
        await call.answer()
        return
    client = await get_ai_client()
    if not client.is_available():
        await call.answer("ИИ-помощник пока не настроен", show_alert=True)
        return
    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer()
        return
    try:
        question_id = int(parts[2])
    except ValueError:
        await call.answer()
        return
    chosen_index: int | None = None
    if len(parts) >= 4 and parts[3] != "":
        try:
            chosen_index = int(parts[3])
        except ValueError:
            chosen_index = None
    user_id = await _check_and_warn(
        call.message, session_factory, settings, call.from_user.id
    )
    if user_id is None:
        await call.answer()
        return
    await call.answer("Думаю...")
    async with session_factory() as db:
        question = await QuestionRepository(db).get_by_id(question_id)
    if question is None:
        await call.message.answer("Не нашёл такой вопрос.")
        return
    placeholder = await call.message.answer("Готовлю развёрнутое объяснение...")
    try:
        result = await elaborate_question(client, question, chosen_index)
    except AIUnavailable:
        await safe_edit_text(placeholder, "ИИ-помощник недоступен. Попробуй позже.")
        return
    except AIError as exc:
        await safe_edit_text(
            placeholder,
            f"Не получилось получить ответ от ИИ: {escape(str(exc)[:200])}",
        )
        return
    async with session_factory() as db:
        await record_usage(db, user_id, "elaborate", result)
        await db.commit()
    await safe_edit_text(
        placeholder,
        _format_ai_reply("Подробнее", result.text, result.provider),
        reply_markup=_elaborate_keyboard(),
    )


__all__ = ["router"]

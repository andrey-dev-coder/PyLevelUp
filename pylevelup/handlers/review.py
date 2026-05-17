from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.categories import display_name
from pylevelup.db.models import Question
from pylevelup.repositories import (
    BookmarkRepository,
    QuestionRepository,
    UserRepository,
)
from pylevelup.services.review_cache import ReviewCache
from pylevelup.utils.edit import edit_or_send, safe_edit_text
from pylevelup.utils.text import format_code_block

router = Router(name="review")


class ReviewStates(StatesGroup):
    viewing = State()


async def _get_user_id(session_factory: async_sessionmaker, telegram_id: int) -> int | None:
    async with session_factory() as db:
        user = await UserRepository(db).get_by_telegram_id(telegram_id)
        return user.id if user else None


def _format_review_question(q: Question, index: int, total: int) -> str:
    lines: list[str] = [
        f"<b>Разбор ошибок · {index + 1} из {total}</b>",
        f"<i>{escape(display_name(q.topic))}</i>",
        "",
        escape(q.text),
    ]
    code_block = format_code_block(q.code, q.code_language)
    if code_block:
        lines.append("")
        lines.append(code_block)
    lines.append("")
    lines.append("<b>Варианты:</b>")
    for idx, opt in enumerate(q.options):
        marker = "✅" if idx == q.correct_index else "  "
        lines.append(f"{marker} <b>{idx + 1}.</b> {escape(opt)}")
    if q.explanation:
        lines.append("")
        lines.append(f"<b>Пояснение:</b> {escape(q.explanation)}")
    return "\n".join(lines)


def _review_kb(index: int, total: int, bookmarked: bool) -> InlineKeyboardMarkup:
    is_last = index >= total - 1
    bm_label = "🔖 В закладках" if bookmarked else "🔖 В закладки"
    rows: list[list[InlineKeyboardButton]] = []
    if is_last:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Понял",
                    callback_data=f"review:got:{index}",
                ),
                InlineKeyboardButton(text=bm_label, callback_data=f"review:bm:{index}"),
            ]
        )
        rows.append(
            [InlineKeyboardButton(text="📊 Итоги", callback_data="review:done")]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Понял",
                    callback_data=f"review:got:{index}",
                ),
                InlineKeyboardButton(text=bm_label, callback_data=f"review:bm:{index}"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="Пропустить →",
                    callback_data=f"review:got:{index}",
                ),
                InlineKeyboardButton(
                    text="📊 Итоги",
                    callback_data="review:done",
                ),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_index(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    review_cache: ReviewCache,
    state: FSMContext,
    user_id: int,
    index: int,
) -> None:
    if call.message is None:
        return
    wrong_ids = await review_cache.load(user_id)
    if not wrong_ids:
        await safe_edit_text(call.message, "Разбор завершён - больше ошибок нет.")
        await state.clear()
        return
    if index >= len(wrong_ids):
        await _show_done(call, state, wrong_ids_count=len(wrong_ids))
        return
    qid = wrong_ids[index]
    async with session_factory() as db:
        q = await QuestionRepository(db).get_by_id(qid)
        bookmarked = (
            await BookmarkRepository(db).is_bookmarked(user_id, qid) if q else False
        )
    if q is None:
        new_ids = [i for i in wrong_ids if i != qid]
        await review_cache.save(user_id, new_ids)
        await _render_index(
            call, session_factory, review_cache, state, user_id, index
        )
        return
    text = _format_review_question(q, index, len(wrong_ids))
    await safe_edit_text(
        call.message,
        text,
        reply_markup=_review_kb(index, len(wrong_ids), bookmarked),
    )
    await state.set_state(ReviewStates.viewing)
    await state.update_data(review_index=index)


async def _show_done(
    call: CallbackQuery,
    state: FSMContext,
    wrong_ids_count: int,
) -> None:
    if call.message is None:
        return
    text = (
        "<b>Разбор окончен</b>\n\n"
        f"Прошёл {wrong_ids_count} ошибочных вопросов. "
        "Запусти ещё через /test, чтобы закрепить."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Запустить ещё", callback_data="menu:test"),
                InlineKeyboardButton(text="Моя статистика", callback_data="stats:show"),
            ]
        ]
    )
    await safe_edit_text(call.message, text, reply_markup=kb)
    await state.clear()


@router.callback_query(F.data == "review:start")
async def handle_review_start(
    callback: CallbackQuery,
    session_factory: async_sessionmaker,
    review_cache: ReviewCache,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return
    user_id = await _get_user_id(session_factory, callback.from_user.id)
    if user_id is None:
        await edit_or_send(callback.message, "Пользователь не найден.")
        return
    wrong_ids = await review_cache.load(user_id)
    if not wrong_ids:
        await edit_or_send(
            callback.message,
            "Ошибок нет - или сессия уже разобрана.",
        )
        await state.clear()
        return
    await _render_index(
        callback, session_factory, review_cache, state, user_id, 0
    )


@router.callback_query(F.data.startswith("review:got:"))
async def handle_review_got(
    callback: CallbackQuery,
    session_factory: async_sessionmaker,
    review_cache: ReviewCache,
    state: FSMContext,
) -> None:
    await callback.answer("Дальше")
    if callback.data is None or callback.from_user is None:
        return
    parts = callback.data.split(":")
    try:
        index = int(parts[2])
    except (IndexError, ValueError):
        return
    user_id = await _get_user_id(session_factory, callback.from_user.id)
    if user_id is None:
        return
    await _render_index(
        callback, session_factory, review_cache, state, user_id, index + 1
    )


@router.callback_query(F.data.startswith("review:bm:"))
async def handle_review_bookmark(
    callback: CallbackQuery,
    session_factory: async_sessionmaker,
    review_cache: ReviewCache,
    state: FSMContext,
) -> None:
    if callback.data is None or callback.from_user is None:
        await callback.answer()
        return
    parts = callback.data.split(":")
    try:
        index = int(parts[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    user_id = await _get_user_id(session_factory, callback.from_user.id)
    if user_id is None:
        await callback.answer()
        return
    wrong_ids = await review_cache.load(user_id)
    if not wrong_ids or index >= len(wrong_ids):
        await callback.answer()
        return
    qid = wrong_ids[index]
    async with session_factory() as db:
        repo = BookmarkRepository(db)
        already = await repo.is_bookmarked(user_id, qid)
        if already:
            await repo.remove(user_id, qid)
            await db.commit()
            await callback.answer("Убрано из закладок")
        else:
            await repo.add(user_id, qid)
            await db.commit()
            await callback.answer("Добавлено в закладки")
    await _render_index(
        callback, session_factory, review_cache, state, user_id, index
    )


@router.callback_query(F.data == "review:done")
async def handle_review_done(
    callback: CallbackQuery,
    session_factory: async_sessionmaker,
    review_cache: ReviewCache,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.from_user is None:
        return
    user_id = await _get_user_id(session_factory, callback.from_user.id)
    if user_id is None:
        return
    wrong_ids = await review_cache.load(user_id)
    await _show_done(callback, state, wrong_ids_count=len(wrong_ids))

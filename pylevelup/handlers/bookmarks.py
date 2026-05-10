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

from pylevelup.db.models import User
from pylevelup.repositories import BookmarkRepository, UserRepository
from pylevelup.services.achievement_evaluator import evaluate_and_grant
from pylevelup.services.achievement_notify import notify_user_about_codes
from pylevelup.utils.edit import safe_edit_text
from pylevelup.utils.text import clean_text

router = Router(name="pylevelup_bookmarks")

PAGE_SIZE = 5


def _list_keyboard(page: int, total: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="← Назад", callback_data=f"bm:list:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="Вперёд →", callback_data=f"bm:list:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _resolve_user(session_factory: async_sessionmaker, telegram_id: int) -> User | None:
    async with session_factory() as db:
        return await UserRepository(db).get_by_telegram_id(telegram_id)


@router.callback_query(F.data.startswith("bm:toggle:"))
async def handle_toggle(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    bot: Bot,
) -> None:
    if call.from_user is None or call.data is None or call.message is None:
        await call.answer()
        return
    parts = call.data.split(":", 2)
    if len(parts) != 3 or not parts[2].isdigit():
        await call.answer()
        return
    question_id = int(parts[2])
    user = await _resolve_user(session_factory, call.from_user.id)
    if user is None:
        await call.answer("Сначала /start", show_alert=True)
        return
    async with session_factory() as db:
        repo = BookmarkRepository(db)
        added = await repo.toggle(user.id, question_id)
        await db.commit()
    await call.answer("Добавлено в закладки" if added else "Убрано из закладок")
    current_markup = call.message.reply_markup
    if current_markup is None:
        return
    star = "★" if added else "☆"
    new_label = f"{star} В закладки"
    new_rows: list[list[InlineKeyboardButton]] = []
    for row in current_markup.inline_keyboard:
        new_row: list[InlineKeyboardButton] = []
        for btn in row:
            if btn.callback_data == f"bm:toggle:{question_id}":
                new_row.append(
                    InlineKeyboardButton(text=new_label, callback_data=btn.callback_data)
                )
            else:
                new_row.append(btn)
        new_rows.append(new_row)
    try:
        await call.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=new_rows)
        )
    except Exception:
        pass
    if added:
        async with session_factory() as db:
            new_codes = await evaluate_and_grant(db, user.id)
            await db.commit()
        if new_codes:
            await notify_user_about_codes(bot, call.from_user.id, new_codes)


async def _build_list_content(
    session_factory: async_sessionmaker,
    telegram_id: int,
    page: int = 0,
) -> tuple[str, InlineKeyboardMarkup] | None:
    user = await _resolve_user(session_factory, telegram_id)
    if user is None:
        return None
    async with session_factory() as db:
        repo = BookmarkRepository(db)
        total = await repo.count(user.id)
        questions = await repo.list_questions(
            user.id, limit=PAGE_SIZE, offset=page * PAGE_SIZE
        )
    if total == 0:
        return (
            "Закладок пока нет. Добавляй вопросы кнопкой ☆ во время теста или изучения.",
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="В главное меню", callback_data="menu:main")]
                ]
            ),
        )
    if not questions and page > 0:
        return await _build_list_content(session_factory, telegram_id, 0)
    header = f"<b>Твои закладки</b> ({total} всего, страница {page + 1})"
    lines = [header, ""]
    for index, q in enumerate(questions, start=1 + page * PAGE_SIZE):
        snippet = clean_text(q.text)
        if len(snippet) > 200:
            snippet = snippet[:200].rstrip() + "..."
        lines.append(f"<b>{index}. [{escape(q.topic)}]</b>")
        lines.append(escape(snippet))
        lines.append("")
    return "\n".join(lines).rstrip(), _list_keyboard(page, total)


@router.message(Command("bookmarks"))
async def handle_bookmarks_command(
    message: Message,
    session_factory: async_sessionmaker,
) -> None:
    if message.from_user is None:
        return
    content = await _build_list_content(session_factory, message.from_user.id, page=0)
    if content is None:
        await message.answer("Сначала /start.")
        return
    text, markup = content
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "bookmarks:show")
async def handle_bookmarks_show(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.from_user is None or call.message is None:
        await call.answer()
        return
    await call.answer()
    content = await _build_list_content(session_factory, call.from_user.id, page=0)
    if content is None:
        await call.message.answer("Сначала /start.")
        return
    text, markup = content
    await safe_edit_text(call.message, text, reply_markup=markup)


@router.callback_query(F.data.startswith("bm:list:"))
async def handle_bookmarks_page(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.from_user is None or call.message is None or call.data is None:
        await call.answer()
        return
    parts = call.data.split(":", 2)
    if len(parts) != 3 or not parts[2].isdigit():
        await call.answer()
        return
    page = int(parts[2])
    await call.answer()
    content = await _build_list_content(session_factory, call.from_user.id, page=page)
    if content is None:
        await call.message.answer("Сначала /start.")
        return
    text, markup = content
    await safe_edit_text(call.message, text, reply_markup=markup)


__all__ = ["router"]

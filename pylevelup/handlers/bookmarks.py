from html import escape

from aiogram import F, Router
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


async def _show_list(
    target_message: Message,
    session_factory: async_sessionmaker,
    telegram_id: int,
    page: int = 0,
) -> None:
    user = await _resolve_user(session_factory, telegram_id)
    if user is None:
        await target_message.answer("Сначала /start.")
        return
    async with session_factory() as db:
        repo = BookmarkRepository(db)
        total = await repo.count(user.id)
        questions = await repo.list_questions(
            user.id, limit=PAGE_SIZE, offset=page * PAGE_SIZE
        )
    if total == 0:
        await target_message.answer(
            "Закладок пока нет. Добавляй вопросы кнопкой ☆ во время теста или изучения."
        )
        return
    if not questions and page > 0:
        await _show_list(target_message, session_factory, telegram_id, 0)
        return
    header = f"<b>Твои закладки</b> ({total} всего, страница {page + 1})"
    lines = [header, ""]
    for index, q in enumerate(questions, start=1 + page * PAGE_SIZE):
        snippet = clean_text(q.text)
        if len(snippet) > 200:
            snippet = snippet[:200].rstrip() + "..."
        lines.append(f"<b>{index}. [{escape(q.topic)}]</b>")
        lines.append(escape(snippet))
        lines.append("")
    await target_message.answer(
        "\n".join(lines).rstrip(),
        reply_markup=_list_keyboard(page, total),
    )


@router.message(Command("bookmarks"))
async def handle_bookmarks_command(
    message: Message,
    session_factory: async_sessionmaker,
) -> None:
    if message.from_user is None:
        return
    await _show_list(message, session_factory, message.from_user.id, page=0)


@router.callback_query(F.data == "bookmarks:show")
async def handle_bookmarks_show(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    if call.from_user is None or call.message is None:
        await call.answer()
        return
    await call.answer()
    await _show_list(call.message, session_factory, call.from_user.id, page=0)


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
    await _show_list(call.message, session_factory, call.from_user.id, page=page)


__all__ = ["router"]

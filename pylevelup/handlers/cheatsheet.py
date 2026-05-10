from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from pylevelup.cheatsheets import CHEATSHEETS, get_cheatsheet
from pylevelup.utils.edit import safe_edit_text

router = Router(name="pylevelup_cheatsheet")


def _list_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for sheet in CHEATSHEETS:
        rows.append(
            [InlineKeyboardButton(text=sheet.title, callback_data=f"cs:show:{sheet.key}")]
        )
    rows.append([InlineKeyboardButton(text="В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="К списку шпаргалок", callback_data="cheatsheet:show")],
            [InlineKeyboardButton(text="В главное меню", callback_data="menu:main")],
        ]
    )


def _list_text() -> str:
    return (
        "<b>Шпаргалки</b>\n\n"
        "Короткие справочники по самым востребованным темам. Выбери раздел:"
    )


@router.message(Command("cheatsheet"))
async def handle_cheatsheet_command(message: Message) -> None:
    await message.answer(_list_text(), reply_markup=_list_keyboard())


@router.callback_query(F.data == "cheatsheet:show")
async def handle_cheatsheet_show(call: CallbackQuery) -> None:
    if call.message is None:
        await call.answer()
        return
    await call.answer()
    await safe_edit_text(call.message, _list_text(), reply_markup=_list_keyboard())


@router.callback_query(F.data.startswith("cs:show:"))
async def handle_cheatsheet_pick(call: CallbackQuery) -> None:
    if call.message is None or call.data is None:
        await call.answer()
        return
    key = call.data.split(":", 2)[2]
    sheet = get_cheatsheet(key)
    if sheet is None:
        await call.answer("Раздел не найден", show_alert=True)
        return
    await call.answer()
    text = f"<b>{sheet.title}</b>\n\n{sheet.body}"
    await safe_edit_text(call.message, text, reply_markup=_back_keyboard())


__all__ = ["router"]

from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


async def edit_or_send(
    call: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs: Any,
) -> Message:
    message = call.message
    if message is None:
        raise RuntimeError("CallbackQuery has no message")
    try:
        edited = await message.edit_text(text, reply_markup=reply_markup, **kwargs)
        if isinstance(edited, Message):
            return edited
        return message
    except TelegramBadRequest:
        return await message.answer(text, reply_markup=reply_markup, **kwargs)


async def safe_edit_text(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs: Any,
) -> Message:
    try:
        edited = await message.edit_text(text, reply_markup=reply_markup, **kwargs)
        if isinstance(edited, Message):
            return edited
        return message
    except TelegramBadRequest:
        return await message.answer(text, reply_markup=reply_markup, **kwargs)


async def safe_edit_markup(
    message: Message,
    reply_markup: InlineKeyboardMarkup | None,
) -> None:
    try:
        await message.edit_reply_markup(reply_markup=reply_markup)
    except TelegramBadRequest:
        pass


__all__ = ["edit_or_send", "safe_edit_text", "safe_edit_markup"]

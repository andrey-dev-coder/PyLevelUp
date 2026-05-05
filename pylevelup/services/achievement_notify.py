from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from pylevelup.services.achievements import ACHIEVEMENTS_BY_CODE


def _format_codes(codes: list[str]) -> str:
    parts: list[str] = ["<b>Новая ачивка!</b>" if len(codes) == 1 else "<b>Новые ачивки!</b>"]
    for code in codes:
        item = ACHIEVEMENTS_BY_CODE.get(code)
        if item is None:
            continue
        parts.append(f"{item.icon} <b>{escape(item.title)}</b> - {escape(item.description)}")
    return "\n".join(parts)


async def notify_user_about_codes(bot: Bot, telegram_id: int, codes: list[str]) -> None:
    if not codes:
        return
    try:
        await bot.send_message(telegram_id, _format_codes(codes))
    except TelegramAPIError:
        pass


__all__ = ["notify_user_about_codes"]

from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.config import Settings
from pylevelup.repositories import (
    ACCESS_CODE_KEY,
    SettingsRepository,
    UserRepository,
)

router = Router(name="pylevelup_admin")


def _is_owner(message: Message, settings: Settings) -> bool:
    return message.from_user is not None and message.from_user.id == settings.owner_telegram_id


async def _resolve_target(repo: UserRepository, raw: str):
    raw = raw.strip()
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        return await repo.get_by_telegram_id(int(raw))
    return await repo.find_by_username(raw)


@router.message(Command("setcode"))
async def handle_setcode(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(message, settings):
        return
    new_code = (command.args or "").strip()
    if not new_code:
        await message.answer(
            "Использование: /setcode НОВОЕ_КОДОВОЕ_СЛОВО\n"
            "Слово может содержать пробелы; всё после команды берётся целиком."
        )
        return
    if len(new_code) < 3:
        await message.answer("Кодовое слово должно быть длиной хотя бы 3 символа.")
        return

    async with session_factory() as db:
        settings_repo = SettingsRepository(db)
        await settings_repo.set(ACCESS_CODE_KEY, new_code)
        await db.commit()
    await message.answer(
        f"Кодовое слово обновлено. Новые пользователи теперь должны вводить:\n"
        f"<code>{escape(new_code)}</code>"
    )


@router.message(Command("getcode"))
async def handle_getcode(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(message, settings):
        return
    async with session_factory() as db:
        settings_repo = SettingsRepository(db)
        code = await settings_repo.get_or_create(ACCESS_CODE_KEY, settings.default_access_code)
        await db.commit()
    await message.answer(f"Текущее кодовое слово:\n<code>{escape(code)}</code>")


@router.message(Command("ban"))
async def handle_ban(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(message, settings):
        return
    target = (command.args or "").strip()
    if not target:
        await message.answer("Использование: /ban TELEGRAM_ID или /ban @username")
        return
    async with session_factory() as db:
        repo = UserRepository(db)
        existing = await _resolve_target(repo, target)
        if existing is None:
            await message.answer("Пользователь не найден в базе.")
            return
        if existing.telegram_id == settings.owner_telegram_id:
            await message.answer("Нельзя забанить владельца бота.")
            return
        await repo.set_banned(existing.telegram_id, banned=True)
        await db.commit()
    await message.answer(
        f"Пользователь <code>{existing.telegram_id}</code> "
        f"({escape(existing.username or existing.first_name or 'без имени')}) забанен."
    )


@router.message(Command("unban"))
async def handle_unban(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(message, settings):
        return
    target = (command.args or "").strip()
    if not target:
        await message.answer("Использование: /unban TELEGRAM_ID или /unban @username")
        return
    async with session_factory() as db:
        repo = UserRepository(db)
        existing = await _resolve_target(repo, target)
        if existing is None:
            await message.answer("Пользователь не найден в базе.")
            return
        await repo.set_banned(existing.telegram_id, banned=False)
        await db.commit()
    await message.answer(
        f"Бан с пользователя <code>{existing.telegram_id}</code> снят. "
        "Чтобы вернуться, ему нужно снова ввести кодовое слово."
    )


@router.message(Command("users"))
async def handle_users(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(message, settings):
        return
    async with session_factory() as db:
        repo = UserRepository(db)
        users = await repo.list_for_admin(limit=50)
    if not users:
        await message.answer("В базе пока нет пользователей.")
        return
    lines = ["<b>Пользователи (последние 50):</b>", ""]
    for u in users:
        flags: list[str] = []
        if u.telegram_id == settings.owner_telegram_id:
            flags.append("owner")
        if u.is_banned:
            flags.append("banned")
        elif u.is_authorized:
            flags.append("authorized")
        else:
            flags.append("pending")
        flag_text = ", ".join(flags)
        username = f"@{u.username}" if u.username else (u.first_name or "")
        lines.append(
            f"<code>{u.telegram_id}</code> {escape(username)} - {flag_text}"
        )
    await message.answer("\n".join(lines))
